---
name: portfolio-data-verification
description: Best practices for auditing and aligning portfolio metrics (NLV, Profit, Cash) between database transactions and external broker API states.
---

# Portfolio Data Verification Skill

This skill defines the methodology for ensuring data integrity and preventing "unexplained" historical noise in the transaction ledger.

## 1. Metric Definitions & Formulas [v2.2]

- **資產淨值 (NLV)**: `Cash Balance + Total Portfolio Equity`.
- **投資組合權益 (Portfolio Equity)**: `Sum( (Quantity * Current Price) / Leverage )`.

## 2. History-Aware Sync Logic [NEW]

To avoid duplicate adjustments (as seen in multiple $297.82 entries):

1. **Idempotency Rule**: The system must check for existing `ETORO_SYNC` entries for the same user, same day, and similar amount before inserting a new one.
2. **Audit Trail Linkage**: All sync records must contain a `raw_data` trace linking the adjustment to the specific snapshot of `BrokerCash` and `LocalCash`.

## 3. eToro Inference & Management

### Categorization (Inference Logic)

- **If Unexplained Movement exists**:
  - Check `totalFees`: Represents dividends or overnight fees.
  - Check `netProfit` from `Trade History`: Relates to closed positions.
  - **Remainder**: Must be classified as `DEPOSIT` or `WITHDRAWAL`.

### Data Cleanup Procedure

If the `Audit Trail` contains redundant sync records (e.g., multiple entries for the same calibration), use the following SQL pattern to identify and prune:

```sql
-- Identify redundant syncs
SELECT trade_date, amount, action, count(*) 
FROM transactions 
WHERE source_file = 'ETORO_SYNC' 
GROUP BY trade_date, amount, action 
HAVING count(*) > 1;

-- Prune metadata-less duplicates
DELETE FROM transactions 
WHERE source_file = 'ETORO_SYNC' AND raw_data IS NULL;
```

## 4. Preventing "Phantom" Drift

1. **Thresholds**: Small drifts (< $0.50) are suppressed.
2. **Safety Caps**: Large drifts (> $500) trigger a manual review request instead of automatic sync.
3. **Traceability**: If a sync occurs, the `raw_data` must explain **exactly** which component lacked history (e.g., "Missing Withdrawal Record").

## 6. 多帳號隔離與歷史重建標準 [v2.3]

### 多帳號治理 (Multi-Account Governance)

1. **帳號標識**：所有交易必須帶有 `source_file` (Account ID)，嚴禁無主交易。
2. **隔離計算**：`TransactionRepository` 與 `AnalyticsService` 必須強制支持按 `account_id` 過濾，避免 A 帳號的入金被計入 B 帳號的損益結構。

### 歷史優先重建 (History-First Reconstruction)

1. **單源真實性**：儀表板趨勢圖與投入資本指標必須優先從交易帳單（Ledger）重建，而非僅依賴每日快照（Snapshots）。
2. **對帳標準**：
   - `nlv_reconstructed = current_cash + Sum(qty * historical_price)`
   - `invested_reconstructed = Sum(Deposits) - Sum(Withdrawals)`
3. **驗證週期**：每次新增非標準化數據（如 CSV 匯入）後，必須觸發 `reconstruct_history` 以驗證資料一致性。
