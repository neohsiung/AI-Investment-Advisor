-- 修正 cash_flows 和 daily_snapshots (無 user_id 欄)
INSERT INTO cash_flows (id, date, amount, type, description)
VALUES
    ('cf-init-2026-01-05', '2026-01-05', 900.00, 'deposit', '初始存款'),
    ('cf-monthly-2026-02-01', '2026-02-01', 100.00, 'deposit', '二月定期投入'),
    ('cf-dividend-2026-02-15', '2026-02-15', 37.73, 'dividend', 'AAPL 股利')
ON CONFLICT (id) DO NOTHING;

-- daily_snapshots 插入 (檢查實際欄位)
-- 先查詢表結構
\d daily_snapshots

-- 投資組合摘要
SELECT 
  'Positions (已投資)' as category,
  ROUND(SUM(market_value)::numeric, 2) as amount
FROM positions
UNION ALL
SELECT 'Available Cash', 700.73
UNION ALL
SELECT 'Unrealized Gains', 121.76
UNION ALL
SELECT 'Total Account Value', 1137.13;

-- 驗證持倉
SELECT ticker, quantity, avg_cost, current_price, market_value, unrealized_pl
FROM positions
ORDER BY ticker;

-- 驗證交易
SELECT id, ticker, trade_date, action, quantity, price, amount
FROM transactions
WHERE user_id = '90693c07-6177-42df-97d9-915f3ce7c573'
ORDER BY trade_date;
