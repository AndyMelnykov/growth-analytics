"""Read the raw files into plain dicts without ever raising on bad content.

Problems with the files themselves (missing, unparseable lines) are recorded on
the Snapshot so check A1 can report them; every other check works on whatever
records did parse.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

SOURCE_FILES: dict[str, str] = {
    "user_signups": "user_signups.jsonl",
    "marketing_attribution": "marketing_attribution.jsonl",
    "conversions": "conversions.jsonl",
    "subscription_events": "subscription_events.jsonl",
    "feature_usage_events": "feature_usage_events.jsonl",
    "feature_releases": "feature_releases.json",
}
METADATA_FILE = "_feature_users_metadata.json"
METADATA_KEY = "_metadata"

_DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_TIMESTAMP_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}")


@dataclass(frozen=True)
class Snapshot:
    records: dict[str, list[dict]]
    missing_files: tuple[str, ...] = ()
    parse_errors: dict[str, tuple[str, ...]] = field(default_factory=dict)
    metadata: dict | None = None


def as_int(v: object) -> int | None:
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def as_date(v: object) -> date | None:
    if not isinstance(v, str) or not _DATE_RE.fullmatch(v):
        return None
    try:
        return date.fromisoformat(v)
    except ValueError:
        return None


def as_timestamp(v: object) -> datetime | None:
    if not isinstance(v, str) or not _TIMESTAMP_RE.fullmatch(v):
        return None
    try:
        return datetime.strptime(v, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def event_date(v: object) -> date | None:
    """The calendar date of a date or a timestamp string."""
    parsed = as_date(v)
    if parsed is not None:
        return parsed
    ts = as_timestamp(v)
    return ts.date() if ts is not None else None


def row_counts(snap: Snapshot) -> dict[str, int]:
    return {name: len(rows) for name, rows in snap.records.items()}


def _read_jsonl(path: Path) -> tuple[list[dict], list[str]]:
    rows: list[dict] = []
    errors: list[str] = []
    for number, raw in enumerate(path.read_bytes().split(b"\n"), start=1):
        try:
            text = raw.decode("utf-8").strip()
        except UnicodeDecodeError as exc:
            errors.append(f"line {number}: invalid UTF-8 ({exc.reason})")
            continue
        if not text:
            continue
        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            errors.append(f"line {number}: not valid JSON ({exc.msg})")
            continue
        if isinstance(value, dict):
            rows.append(value)
        else:
            errors.append(f"line {number}: expected a JSON object, got {type(value).__name__}")
    return rows, errors


def _load_json(path: Path) -> tuple[object, str | None]:
    try:
        return json.loads(path.read_bytes().decode("utf-8")), None
    except UnicodeDecodeError as exc:
        return None, f"invalid UTF-8 ({exc.reason})"
    except json.JSONDecodeError as exc:
        return None, f"not valid JSON ({exc.msg})"


def _read_json_array(path: Path) -> tuple[list[dict], list[str]]:
    value, error = _load_json(path)
    if error is not None:
        return [], [error]
    if not isinstance(value, list):
        return [], [f"expected a JSON array, got {type(value).__name__}"]
    rows = [item for item in value if isinstance(item, dict)]
    errors = [
        f"item {i}: expected a JSON object, got {type(item).__name__}"
        for i, item in enumerate(value, start=1)
        if not isinstance(item, dict)
    ]
    return rows, errors


def _read_metadata(path: Path) -> tuple[dict | None, str | None]:
    value, error = _load_json(path)
    if error is not None:
        return None, error
    if not isinstance(value, dict):
        return None, f"expected a JSON object, got {type(value).__name__}"
    return value, None


def load_snapshot(raw_dir: Path | str) -> Snapshot:
    raw = Path(raw_dir)
    if not raw.is_dir():
        raise FileNotFoundError(f"raw data directory not found: {raw}")

    records: dict[str, list[dict]] = {}
    missing: list[str] = []
    parse_errors: dict[str, tuple[str, ...]] = {}
    for source, file_name in SOURCE_FILES.items():
        path = raw / file_name
        if not path.is_file():
            records[source] = []
            missing.append(file_name)
            continue
        reader = _read_jsonl if file_name.endswith(".jsonl") else _read_json_array
        records[source], errors = reader(path)
        if errors:
            parse_errors[source] = tuple(errors)

    metadata = None
    meta_path = raw / METADATA_FILE
    if meta_path.is_file():
        metadata, error = _read_metadata(meta_path)
        if error is not None:
            parse_errors[METADATA_KEY] = (error,)

    return Snapshot(
        records=records,
        missing_files=tuple(missing),
        parse_errors=parse_errors,
        metadata=metadata,
    )
