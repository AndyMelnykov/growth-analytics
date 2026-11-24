"""Which usage patterns move conversion and the paid lifecycle, as a graph.

Two analyses over the raw snapshot (feature usage, conversions, subscription
events), both time-aware so that usage after an outcome can never explain it:

1. Driver rates. For every user-day at risk of an outcome, a behaviour counts
   as "done" only if it happened on an earlier day. Conversion rates per
   user-day with and without the behaviour are compared inside strata
   (days-since-signup band x signup month, or days-since-purchase band x plan
   for the paid lifecycle) and pooled with a Mantel-Haenszel rate ratio and a
   Greenland-Robins 95% interval. Feature behaviours only count unexposed days
   on which the feature had been released.

2. Journey graph. Pre-purchase event sequences become a weighted directed
   graph Signup -> feature -> ... -> Converted | Not converted, built with
   `graph.build.build_graph`. Treated as an absorbing Markov chain it gives,
   per feature, the probability of converting from that point and the share
   of conversions lost if the feature were removed (removal effect).

Run: python -m graph.usage_conversion --out usage_conversion.json \
         --deck docs/reports/usage-to-purchase-deck.html
Requires the `graph` and `funnels` extras (igraph, DuckDB).
"""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

from graph.build import build_graph

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"
DATA_END = "2024-12-31"
MAX_DAYS_TO_CONVERT = 95  # longest observed; every signup has this much follow-up
FEATURES = [
    "real_time_collab", "ai_insights", "advanced_export",
    "api_access", "team_analytics", "custom_workflows",
]
START, CONVERTED, NOT_CONVERTED = "Signup", "Converted", "Not converted"

# Behaviours shown in the graph and the report (label, kind). Feature-level
# view/use/share rows are computed too and kept in the JSON for drill-down.
PATTERNS = {
    "use_any": "Used any feature",
    "share_any": "Shared from any feature",
    "breadth_2": "Used 2+ features",
    "breadth_3": "Used 3+ features",
    "active_3d": "Active on 3+ days",
    "active_7d": "Active on 7+ days",
    "events_10": "10+ events",
    "never_active": "No activity yet",
    "view_only": "Viewed but never used",
    "dormant_14": "Inactive 14+ days",
}


def _sql(raw: Path) -> str:
    r = raw.as_posix()
    return f"""
create table users as
select s.user_id, s.signup_date::date as signup_date,
       c.conversion_date::date as conv_date, c.plan
from read_json_auto('{r}/user_signups.jsonl') s
left join read_json_auto('{r}/conversions.jsonl') c using (user_id);

create table ev as
select user_id, feature_name as feature, event_type,
       cast("timestamp" as timestamp) as ts, cast("timestamp" as date) as d
from read_json_auto('{r}/feature_usage_events.jsonl');

create table rel as
select name as feature, min(release_date)::date as released
from read_json('{r}/feature_releases.json') group by 1;

create table sub as
select user_id, event_type, event_date::date as d
from read_json_auto('{r}/subscription_events.jsonl');

-- First date of each monotone behaviour (once done, a user stays "exposed").
create table bf as
with fu as (
    select user_id, feature, min(d) as d from ev where event_type = 'use' group by all
), days as (
    select user_id, d, row_number() over (partition by user_id order by d) as k
    from (select distinct user_id, d from ev)
), nth_event as (
    select user_id, d, row_number() over (partition by user_id order by ts) as k from ev
)
select user_id, event_type || ':' || feature as behavior, feature, min(d) as first_d
from ev group by all
union all select user_id, 'any:' || feature, feature, min(d) from ev group by all
union all select user_id, 'use_any', null, min(d) from ev where event_type = 'use' group by all
union all select user_id, 'share_any', null, min(d) from ev where event_type = 'share' group by all
union all select user_id, 'breadth_2', null, d from (
    select user_id, d, row_number() over (partition by user_id order by d, feature) k from fu) where k = 2
union all select user_id, 'breadth_3', null, d from (
    select user_id, d, row_number() over (partition by user_id order by d, feature) k from fu) where k = 3
union all select user_id, 'active_3d', null, d from days where k = 3
union all select user_id, 'active_7d', null, d from days where k = 7
union all select user_id, 'events_10', null, d from nth_event where k = 10;

create table behaviors as select distinct behavior, feature from bf
union all select * from (values ('never_active', null), ('view_only', null), ('dormant_14', null))
    t(behavior, feature);

-- One row per user per day from signup to the end of the data, with the
-- activity state as of the start of that day (events on earlier days only).
create table pd as
with daily as (
    select user_id, d, count(*) as n, count(*) filter (where event_type = 'use') as nu
    from ev group by all
), grid as (
    select u.user_id, u.signup_date, u.conv_date, u.plan,
           (u.signup_date + t.i::integer)::date as day, t.i::integer as tenure
    from users u cross join range(0, 400) t(i)
    where u.signup_date + t.i::integer <= DATE '{DATA_END}'
)
select g.*,
       coalesce(sum(dl.n) over w, 0) as n_before,
       coalesce(sum(dl.nu) over w, 0) as nu_before,
       max(case when dl.n > 0 then g.day end) over w as last_active
from grid g left join daily dl on dl.user_id = g.user_id and dl.d = g.day
window w as (partition by g.user_id order by g.day rows between unbounded preceding and 1 preceding);
"""


def _exposure_agg(con, at_risk_sql: str) -> list[tuple]:
    """(behavior, outcome, stratum, exposed, events, days) for an at-risk day set.

    `at_risk_sql` selects user_id, day, outcome, stratum, event (bool) from pd.
    """
    return con.execute(f"""
        with ar as ({at_risk_sql}),
        flagged as (
            select b.behavior, ar.outcome, ar.stratum, ar.event,
                   case b.behavior
                       when 'never_active' then ar.n_before = 0
                       when 'view_only' then ar.n_before > 0 and ar.nu_before = 0
                       when 'dormant_14' then ar.n_before > 0 and ar.day - ar.last_active > 14
                       else bf.first_d is not null
                   end as exposed,
                   -- Feature behaviours: compare only days on which the feature existed.
                   -- View-only and dormancy: compare only among users already active.
                   (b.feature is null or r.released <= ar.day)
                   and (b.behavior not in ('view_only', 'dormant_14') or ar.n_before > 0) as available
            from ar
            cross join behaviors b
            left join rel r on r.feature = b.feature
            left join bf on bf.user_id = ar.user_id and bf.behavior = b.behavior
                        and bf.first_d < ar.day
        )
        select behavior, outcome, stratum, exposed,
               count(*) filter (where event) as events, count(*) as days
        from flagged where available
        group by all
    """).fetchall()


def _exposed_users(con, at_risk_sql: str) -> dict[tuple[str, str], int]:
    rows = con.execute(f"""
        with ar as ({at_risk_sql})
        select bf.behavior, ar.outcome, count(distinct ar.user_id)
        from ar join bf on bf.user_id = ar.user_id and bf.first_d < ar.day
        group by all
    """).fetchall()
    return {(b, o): n for b, o, n in rows}


def mantel_haenszel(strata: dict) -> dict:
    """Pooled rate ratio over strata of {exposed: (events, days)}."""
    num = den = var_num = 0.0
    a_tot = b_tot = t1_tot = t0_tot = 0
    for cells in strata.values():
        a, t1 = cells.get(True, (0, 0))
        b, t0 = cells.get(False, (0, 0))
        a_tot, b_tot, t1_tot, t0_tot = a_tot + a, b_tot + b, t1_tot + t1, t0_tot + t0
        t = t1 + t0
        if t1 == 0 or t0 == 0:
            continue
        num += a * t0 / t
        den += b * t1 / t
        var_num += (a + b) * t1 * t0 / t**2
    out = {
        "exposed_events": a_tot, "exposed_days": t1_tot,
        "unexposed_events": b_tot, "unexposed_days": t0_tot,
        "exposed_rate_per_1000": 1000 * a_tot / t1_tot if t1_tot else None,
        "unexposed_rate_per_1000": 1000 * b_tot / t0_tot if t0_tot else None,
        "rate_ratio": None, "ci_low": None, "ci_high": None, "significant": False,
    }
    if num > 0 and den > 0:
        rr = num / den
        se = math.sqrt(var_num / (num * den))
        lo, hi = rr * math.exp(-1.96 * se), rr * math.exp(1.96 * se)
        # `robust`: the interval still excludes 1 at z=3.14, i.e. Bonferroni for
        # the ~30 behaviours tested per outcome. Treat `significant` alone as a lead.
        z_strict = 3.14
        out.update(rate_ratio=rr, ci_low=lo, ci_high=hi, significant=lo > 1 or hi < 1,
                   robust=rr * math.exp(-z_strict * se) > 1 or rr * math.exp(z_strict * se) < 1)
    return out


def _pool(rows, exposed_users) -> list[dict]:
    grouped: dict[tuple[str, str], dict] = defaultdict(lambda: defaultdict(dict))
    for behavior, outcome, stratum, exposed, events, days in rows:
        grouped[(behavior, outcome)][stratum][bool(exposed)] = (events, days)
    results = []
    for (behavior, outcome), strata in sorted(grouped.items()):
        res = mantel_haenszel(strata)
        res.update(behavior=behavior, outcome=outcome,
                   exposed_users=exposed_users.get((behavior, outcome)))
        results.append(res)
    return results


PRE_AT_RISK = f"""
    select pd.*, o.outcome,
           (case when pd.tenure < 7 then 'd00-06' when pd.tenure < 14 then 'd07-13'
                 when pd.tenure < 30 then 'd14-29' when pd.tenure < 60 then 'd30-59'
                 else 'd60-95' end) || '|' || strftime(pd.signup_date, '%m') as stratum,
           pd.day = pd.conv_date and (o.outcome = 'converted' or o.outcome = 'converted_' || pd.plan) as event
    from pd cross join (values ('converted'), ('converted_pro'), ('converted_enterprise')) o(outcome)
    where pd.tenure <= {MAX_DAYS_TO_CONVERT} and (pd.conv_date is null or pd.day <= pd.conv_date)
"""

POST_AT_RISK = """
    with firsts as (
        select user_id,
               min(d) filter (where event_type in ('seats_expanded', 'plan_upgraded')) as expansion,
               min(d) filter (where event_type in ('seats_contracted', 'plan_downgraded')) as contraction,
               min(d) filter (where event_type = 'subscription_cancelled') as cancellation
        from sub group by 1
    ), long as (
        select user_id, 'expansion' as outcome, expansion as event_d, cancellation from firsts
        union all select user_id, 'contraction', contraction, cancellation from firsts
        union all select user_id, 'cancellation', cancellation, cancellation from firsts
    )
    select pd.*, l.outcome,
           (case when pd.day - pd.conv_date <= 30 then 'm0-1' when pd.day - pd.conv_date <= 90 then 'm1-3'
                 when pd.day - pd.conv_date <= 180 then 'm3-6' else 'm6+' end) || '|' || pd.plan as stratum,
           pd.day = l.event_d as event
    from pd join long l using (user_id)
    where pd.conv_date is not null and pd.day > pd.conv_date
      and pd.day <= coalesce(l.event_d, DATE '2100-01-01')
      and pd.day <= coalesce(l.cancellation, DATE '2100-01-01')
"""


def journey_graph(con):
    """Pre-purchase Markov journey graph, plus absorption and removal effects."""
    seqs = con.execute(f"""
        select u.user_id, u.conv_date is not null as converted,
               list(e.feature order by e.ts) filter (where e.feature is not null) as path
        from users u
        left join ev e on e.user_id = u.user_id
             and (case when u.conv_date is not null then e.d < u.conv_date
                       else e.d <= u.signup_date + {MAX_DAYS_TO_CONVERT} end)
        group by all
    """).fetchall()
    rows, visits, converted_paths = [], defaultdict(int), defaultdict(int)
    for _uid, converted, path in seqs:
        path = path or []
        end = CONVERTED if converted else NOT_CONVERTED
        chain = [START, *path, end]
        rows.extend((a, b, 1) for a, b in zip(chain, chain[1:]))
        for f in set(path):
            visits[f] += 1
            converted_paths[f] += int(converted)

    g = build_graph(rows)
    names = g.vs["name"]
    out: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for e in g.es:
        out[names[e.source]].append((names[e.target], e["weight"]))

    def absorption(removed: str | None = None) -> dict[str, float]:
        h = {n: 0.0 for n in names}
        h[CONVERTED] = 1.0
        for _ in range(5000):
            delta = 0.0
            for n in names:
                if n in (CONVERTED, NOT_CONVERTED) or n == removed:
                    continue
                total = sum(w for _, w in out[n])
                new = sum(w * h[t] for t, w in out[n]) / total
                delta = max(delta, abs(new - h[n]))
                h[n] = new
            if delta < 1e-12:
                break
        return h

    base = absorption()
    pagerank = dict(zip(names, g.pagerank(weights="weight")))
    nodes = []
    for n in names:
        node = {"id": n, "p_convert": base[n], "pagerank": pagerank[n]}
        if n in FEATURES:
            removed = absorption(removed=n)
            node.update(
                removal_effect=1 - removed[START] / base[START],
                users=visits[n], converted_users=converted_paths[n],
            )
        nodes.append(node)
    edges = []
    for n, targets in out.items():
        total = sum(w for _, w in targets)
        edges.extend({"source": n, "target": t, "count": int(w), "share": w / total} for t, w in targets)
    return {"nodes": nodes, "edges": edges,
            "baseline_p_convert": base[START],
            "users": len(seqs), "vertex_count": g.vcount(), "edge_count": g.ecount()}


def naive_comparison(con):
    """Ever-used-feature conversion rates: the leaky comparison, for contrast."""
    return [
        {"feature": f, "ever_used": n1, "ever_used_conv_rate": r1,
         "pre_purchase_users": n2, "pre_purchase_conv_rate": r2}
        for f, n1, r1, n2, r2 in con.execute("""
            with ever as (select distinct user_id, feature from ev),
            pre as (
                select distinct e.user_id, e.feature from ev e join users u using (user_id)
                where u.conv_date is null or e.d < u.conv_date
            )
            select f.feature,
                   count(distinct ever.user_id),
                   avg((u1.conv_date is not null)::int),
                   (select count(*) from pre p join users u2 using (user_id) where p.feature = f.feature),
                   (select avg((u2.conv_date is not null)::int) from pre p join users u2 using (user_id)
                     where p.feature = f.feature)
            from rel f
            join ever on ever.feature = f.feature
            join users u1 on u1.user_id = ever.user_id
            group by f.feature order by f.feature
        """).fetchall()
    ]


def landmark_intensity(con, landmark: int = 14) -> list[dict]:
    """Cross-check: users still free on day `landmark`, by events before it."""
    rows = con.execute(f"""
        with m as (
            select u.user_id, u.conv_date is not null as converted,
                   count(e.user_id) as n,
                   count(distinct e.feature) filter (where e.event_type = 'use') as features_used
            from users u
            left join ev e on e.user_id = u.user_id and e.d < u.signup_date + {landmark}
            where u.conv_date is null or u.conv_date >= u.signup_date + {landmark}
            group by all
        )
        select case when n = 0 then '0' when n <= 2 then '1-2' when n <= 5 then '3-5' else '6+' end as bucket,
               count(*), count(*) filter (where converted)
        from m group by 1 order by min(n)
    """).fetchall()
    return [{"events_before_landmark": b, "users": n, "converted": k, "rate": k / n} for b, n, k in rows]


def run(raw: Path = RAW) -> dict:
    import duckdb

    con = duckdb.connect()
    con.execute(_sql(raw))
    pre = _pool(_exposure_agg(con, PRE_AT_RISK), _exposed_users(con, PRE_AT_RISK))
    post = _pool(_exposure_agg(con, POST_AT_RISK), _exposed_users(con, POST_AT_RISK))
    summary = con.execute("""
        select count(*), count(conv_date),
               count(*) filter (where plan = 'pro'), count(*) filter (where plan = 'enterprise'),
               (select count(*) from ev),
               (select count(*) from ev join users using (user_id) where conv_date is not null and d >= conv_date),
               (select count(*) from ev join users using (user_id) where conv_date is not null)
        from users
    """).fetchone()
    lifecycle = dict(con.execute("select event_type, count(distinct user_id) from sub group by 1").fetchall())
    return {
        "summary": dict(zip(
            ["users", "converted", "pro", "enterprise", "events",
             "converter_events_after_purchase", "converter_events"], summary)),
        "lifecycle_users": lifecycle,
        "labels": {**PATTERNS,
                   **{f"use:{f}": f"Used {f}" for f in FEATURES},
                   **{f"view:{f}": f"Viewed {f}" for f in FEATURES},
                   **{f"share:{f}": f"Shared {f}" for f in FEATURES},
                   **{f"any:{f}": f"Touched {f}" for f in FEATURES}},
        "pre_purchase": pre,
        "post_purchase": post,
        "journey": journey_graph(con),
        "naive": naive_comparison(con),
        "landmark_day14": landmark_intensity(con),
    }


DECK_TEMPLATE = Path(__file__).with_name("report") / "usage_conversion_deck.html"


def compact(result: dict) -> dict:
    """The subset of `run()` output the slide deck embeds, rounded."""
    def rnd(x, n=3):
        return None if x is None else round(x, n)

    rows = [
        {"b": x["behavior"], "o": x["outcome"], "rr": rnd(x["rate_ratio"]), "lo": rnd(x["ci_low"]),
         "hi": rnd(x["ci_high"]), "sig": x["significant"], "rob": x["robust"],
         "ee": x["exposed_events"], "ue": x["unexposed_events"], "n": x["exposed_users"]}
        for part in ("pre_purchase", "post_purchase") for x in result[part]
        if x["rate_ratio"] is not None
    ]
    j = result["journey"]
    return {
        "summary": result["summary"],
        "lifecycle": result["lifecycle_users"],
        "labels": result["labels"],
        "rows": rows,
        "journey": {
            "base": rnd(j["baseline_p_convert"], 4),
            "nodes": [{k: rnd(v, 4) if isinstance(v, float) else v for k, v in n.items()} for n in j["nodes"]],
            "edges": [{**e, "share": rnd(e["share"], 4)} for e in j["edges"]],
        },
        "naive": [{k: rnd(v, 4) if isinstance(v, float) else v for k, v in n.items()} for n in result["naive"]],
        "landmark": result["landmark_day14"],
    }


def write_deck(result: dict, path: Path) -> None:
    template = DECK_TEMPLATE.read_text(encoding="utf-8")
    data = json.dumps(compact(result), separators=(",", ":"))
    path.write_text(template.replace("/*DATA*/null", data), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=Path("usage_conversion.json"))
    parser.add_argument("--deck", type=Path, help="also write the HTML slide deck to this path")
    args = parser.parse_args()
    result = run()
    args.out.write_text(json.dumps(result, indent=1, default=str))
    print(f"wrote {args.out}")
    if args.deck:
        write_deck(result, args.deck)
        print(f"wrote {args.deck}")


if __name__ == "__main__":
    main()
