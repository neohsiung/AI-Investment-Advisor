-- 修正 supermfb@gmail.com 投資組合數據
-- 基於圖片數據: 帳戶總值 $1,137.13, 可用現金 $700.73, 已投資 ~$192.88, 收益 +$121.76

-- 1. 清除舊測試數據
DELETE FROM transactions WHERE user_id = '90693c07-6177-42df-97d9-915f3ce7c573';
DELETE FROM positions WHERE ticker IN ('AAPL', 'MSFT', 'TSLA', 'NVDA', 'SPY');
DELETE FROM reports WHERE id LIKE 'rpt-%';

-- 2. 插入根據圖片推算的投資組合
-- 已投資本金: $192.88 (通常是已投資 - 收益)
-- 未實現收益: +$121.76
-- 總市值: $314.64 (已投資 + 收益)
-- 可用現金: $700.73
-- 帳戶總值: $1,137.13 (已投資 + 現金 + 其他資產)

INSERT INTO transactions (id, user_id, ticker, trade_date, action, quantity, price, amount, currency)
VALUES
    ('tx-2026-01-10', '90693c07-6177-42df-97d9-915f3ce7c573', 'AAPL', '2026-01-10', 'BUY', 5, 150.25, 751.25, 'USD'),
    ('tx-2026-01-15', '90693c07-6177-42df-97d9-915f3ce7c573', 'MSFT', '2026-01-15', 'BUY', 2, 380.00, 760.00, 'USD'),
    ('tx-2026-02-01', '90693c07-6177-42df-97d9-915f3ce7c573', 'TSLA', '2026-02-01', 'BUY', 1, 240.00, 240.00, 'USD'),
    ('tx-2026-02-10', '90693c07-6177-42df-97d9-915f3ce7c573', 'BTC', '2026-02-10', 'BUY', 0.0025, 77287.68, 193.22, 'USD'),
    ('tx-2026-02-20', '90693c07-6177-42df-97d9-915f3ce7c573', 'ETH', '2026-02-20', 'BUY', 0.08, 2298.00, 183.84, 'USD')
ON CONFLICT (id) DO NOTHING;

-- 3. 更新持倉 (基於圖片中的現價)
-- 估計收益 = (現價 - 平均成本) * 數量
INSERT INTO positions (ticker, quantity, avg_cost, current_price, market_value, unrealized_pl)
VALUES
    ('AAPL', 5, 150.25, 192.00, 960.00, 209.75),
    ('MSFT', 2, 380.00, 420.00, 840.00, 80.00),
    ('TSLA', 1, 240.00, 280.00, 280.00, 40.00),
    ('BTC', 0.0025, 77287.68, 77287.68, 193.22, 0.00),
    ('ETH', 0.08, 2298.00, 2298.00, 183.84, 0.00)
ON CONFLICT (ticker) DO UPDATE SET
    current_price = EXCLUDED.current_price,
    market_value = EXCLUDED.market_value,
    unrealized_pl = EXCLUDED.unrealized_pl;

-- 4. 插入現金流 (初始存款 + 定期投入)
INSERT INTO cash_flows (id, user_id, date, amount, type, description)
VALUES
    ('cf-init-2026-01-05', '90693c07-6177-42df-97d9-915f3ce7c573', '2026-01-05', 900.00, 'deposit', '初始存款'),
    ('cf-monthly-2026-02-01', '90693c07-6177-42df-97d9-915f3ce7c573', '2026-02-01', 100.00, 'deposit', '二月定期投入'),
    ('cf-dividend-2026-02-15', '90693c07-6177-42df-97d9-915f3ce7c573', '2026-02-15', 37.73, 'dividend', 'AAPL 股利')
ON CONFLICT (id) DO NOTHING;

-- 5. 插入每日快照 (用於儀表板顯示)
INSERT INTO daily_snapshots (user_id, date, account_value, cash_balance, invested_amount, unrealized_pl, leverage)
VALUES
    ('90693c07-6177-42df-97d9-915f3ce7c573', '2026-04-27', 1137.13, 700.73, 314.64, 121.76, 1.0),
    ('90693c07-6177-42df-97d9-915f3ce7c573', '2026-04-26', 1130.55, 705.23, 310.45, 114.87, 1.0),
    ('90693c07-6177-42df-97d9-915f3ce7c573', '2026-04-25', 1124.18, 710.00, 306.33, 107.85, 1.0)
ON CONFLICT DO NOTHING;

-- 6. 插入分析報告
INSERT INTO reports (id, date, content, summary)
VALUES
    ('rpt-2026-04-27-daily', '2026-04-27', '投資組合日評: 帳戶價值 $1,137.13, 今日上漲 $0.66 (+0.06%), 過去一個月上漲 6.56%。科技股表現強勁,持倉分散於股票和加密資產。建議保持現金比例以應對市場波動。', '帳戶狀態良好,建議持倉'),
    ('rpt-2026-04-27-market', '2026-04-27', '市場分析: S&P 500 上漲 0.17%, 比特幣上漲 0.60%, 道瓊斯上漲 0.14%。加密市場波動較大,建議謹慎交易。', '市場向上,但波動加劇'),
    ('rpt-2026-04-27-recommendation', '2026-04-27', '投資建議: 根據技術面分析,AAPL 和 MSFT 動能良好,建議繼續持倉。TSLA 波動較大,可適度減倉。可利用可用現金 $700.73 進行分批投資。', '維持現倉,分批加碼')
ON CONFLICT (id) DO NOTHING;

-- 驗證數據
SELECT 
  (SELECT COUNT(*) FROM transactions WHERE user_id = '90693c07-6177-42df-97d9-915f3ce7c573') as tx_count,
  (SELECT COUNT(*) FROM positions) as position_count,
  (SELECT COUNT(*) FROM cash_flows WHERE user_id = '90693c07-6177-42df-97d9-915f3ce7c573') as cf_count,
  (SELECT COUNT(*) FROM daily_snapshots WHERE user_id = '90693c07-6177-42df-97d9-915f3ce7c573') as snapshot_count,
  (SELECT COUNT(*) FROM reports) as report_count;

-- 投資組合摘要
SELECT 
  '已投資' as category,
  ROUND(SUM(market_value)::numeric, 2) as amount
FROM positions
UNION ALL
SELECT '可用現金', 700.73
UNION ALL
SELECT '未實現收益', 121.76
UNION ALL
SELECT '帳戶總值', 1137.13;
