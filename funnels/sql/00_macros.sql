-- Shared helpers. Wilson 95% interval for a proportion k/n (z = 1.96, z^2 = 3.8416).
-- NULL when n = 0 so empty groups never raise a division error.
create or replace macro wilson_low(k, n) as
    case when n > 0 then
        greatest(0.0, (k + 1.9208 - 1.96 * sqrt(k * (n - k) / n + 0.9604)) / (n + 3.8416))
    end;

create or replace macro wilson_high(k, n) as
    case when n > 0 then
        least(1.0, (k + 1.9208 + 1.96 * sqrt(k * (n - k) / n + 0.9604)) / (n + 3.8416))
    end;

create or replace macro safe_rate(k, n) as
    case when n > 0 then k::double / n end;

-- 95% Wald interval for the difference of two proportions k1/n1 - k2/n2.
create or replace macro diff_low(k1, n1, k2, n2) as
    case when n1 > 0 and n2 > 0 then
        (k1::double / n1 - k2::double / n2)
        - 1.96 * sqrt((k1::double / n1) * (1 - k1::double / n1) / n1
                    + (k2::double / n2) * (1 - k2::double / n2) / n2)
    end;

create or replace macro diff_high(k1, n1, k2, n2) as
    case when n1 > 0 and n2 > 0 then
        (k1::double / n1 - k2::double / n2)
        + 1.96 * sqrt((k1::double / n1) * (1 - k1::double / n1) / n1
                    + (k2::double / n2) * (1 - k2::double / n2) / n2)
    end;

-- Buckets of "number of active days", shared by the aha and habit analyses.
create or replace macro activity_bucket(n) as
    case when n = 0 then '0' when n = 1 then '1' when n <= 3 then '2-3'
         when n <= 6 then '4-6' else '7+' end;

create or replace macro activity_bucket_order(n) as
    case when n = 0 then 0 when n = 1 then 1 when n <= 3 then 2
         when n <= 6 then 3 else 4 end;
