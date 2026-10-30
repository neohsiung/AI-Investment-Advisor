-- 唯讀：ETORO_SYNC 去重對 K3/K4 的影響量（DD-2026-1029 §2）。read-only; no writes.
with nav as (select total_nlv n from daily_snapshots where total_nlv is not null order by date desc limit 1),
t as (select id, trade_date::date d, ticker, action, amount, source_file,
        round(quantity::numeric,4) q, price
      from transactions where entry_category='trade' and trade_date >= current_date-30),
sysrows as (select * from t where source_file <> 'ETORO_SYNC'),
flag as (select t.*, (t.source_file='ETORO_SYNC' and exists (
          select 1 from sysrows e where e.action=t.action and e.d=t.d and e.q=t.q
          and abs(e.price-t.price)/nullif(e.price,0)<0.02)) is_dup from t),
v as (
  select 'V0_all(現行)' variant, * from flag
  union all select 'V1_排除全部ETORO_SYNC', * from flag where source_file<>'ETORO_SYNC'
  union all select 'V2_只去掉對得上的重複', * from flag where not is_dup
),
k4 as (select variant, count(*) rows_n, round(sum(amount)::numeric,0) vol,
   round((sum(amount)/2.0/(select n from nav)*365.0/30.0)::numeric,2) turnover_x from v group by 1),
dayk as (select variant, d, sum(amount) filter (where action='SELL') sell_amt,
   count(distinct ticker) filter (where action='SELL') sell_tickers from v group by 1,2),
k3 as (select variant, round(max(sell_amt/(select n from nav)*100)::numeric,1) worst_pct,
   max(sell_tickers) worst_n,
   count(*) filter (where sell_amt/(select n from nav)*100>20) days_over_20pct from dayk group by 1)
select k4.variant, rows_n, vol, turnover_x, worst_pct, worst_n, days_over_20pct
from k4 join k3 using(variant) order by 1;
select (select n from (select total_nlv n from daily_snapshots where total_nlv is not null order by date desc limit 1) x) nav_usd;
