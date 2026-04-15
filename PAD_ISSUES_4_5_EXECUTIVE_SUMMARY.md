# 【PAD】投資顧問 Issue #4-5 根因分析與修復計畫

**時間戳記：** 2026-04-13 | **狀態：** 分析完成 ✅ | **優先級：** 🔴 CRITICAL

---

## 📊 執行摘要

### Issue #4：NLV/P&L 數據同步差異

**症狀：**
- 系統報告：NLV $1,308.24 → eToro $1,105.33 (偏差 +18.3%)
- 系統報告：P&L $1,461.26 → eToro $314.64 (偏差 +364% ⚠️)

**根因：4 個計算錯誤**

| 問題 | 位置 | 影響 | 修復時間 |
|------|------|------|---------|
| NLV 計算包含現金 | `analytics_service.py:62-74` | +$200+ 虛報 | 1h |
| P&L 公式錯誤 | `dashboard_service.py:110-111` | +$1,100+ 虛報 | 2h |
| Invested Capital 誤定義 | `transaction_repository.py` | 級聯誤差 | 1h |
| 無資料源追蹤 | `etoro_service.py` | 無法審計 | 1h |

**修復優先級：**
1. ✏️ 使用 eToro `account.total_equity` 替代本地計算
2. ✏️ P&L = Σ(position unrealized PnL) + (realized PnL)
3. ✏️ 添加 `last_portfolio_fetch_time` 戳記
4. ✏️ 修正 `invested_capital` 定義（僅持倉成本）

**預期效果：** 消除所有數據差異 ✅

---

### Issue #5：排程任務無法執行

**症狀：**
- ❌ 所有排程任務每 4 小時失敗一次
- ✅ 排程進程運行中，但 100% 任務失敗
- 🔴 Broker 同步 0% 成功率

**根因：2 個 CRITICAL 缺陷**

| 問題 | 位置 | 症狀 | 影響 | 修復時間 |
|------|------|------|------|---------|
| Async/Sync 混淆 | `scheduler_service.py:job_etoro_sync()` | `'coroutine' object is not iterable` | 每 4h 失敗 | 10min |
| celery_app.py 損毀 | `src/infrastructure/celery_app.py` | 檔案截斷 | health check 失敗 50/h | 15min |

**最後 5 次執行：全部失敗** ❌

```
10:23 FAILED - 'coroutine' object is not iterable
06:23 FAILED - 'coroutine' object is not iterable  
02:23 FAILED - 'coroutine' object is not iterable
22:23 FAILED - 'coroutine' object is not iterable
18:23 FAILED - 'coroutine' object is not iterable
```

**修復優先級：**
1. 🔴 **IMMEDIATE** — 修復 `job_etoro_sync()` 的 async/await
2. 🔴 **IMMEDIATE** — 恢復 `celery_app.py` (5 行程式碼)
3. 🟡 修復 DB schema (缺列)
4. 🟡 修復 Redis 連接 (可選，快取用)

---

## 🛠️ 修復計畫

### Phase 1：Issue #5 修復 (20 分鐘) ⚡ 最優先

**為什麼先修 #5？**
- 排程任務障礙 → 自動化完全癱瘓
- 修復最快，影響最大

#### 修復 1.1：scheduler_service.py - async/await 修正

**檔案：** `src/services/scheduler_service.py`

```python
# ❌ BEFORE (Line ~85)
def job_etoro_sync():
    result = broker.sync_history()  # Returns coroutine, not awaited!
    return result

# ✅ AFTER
import asyncio

def job_etoro_sync():
    result = asyncio.run(broker.sync_history())
    return result
```

**驗證：**
```bash
cd ~/Work/Projects/AI/investment-advisor
python -c "from src.services.scheduler_service import job_etoro_sync; job_etoro_sync()"
# Should complete without coroutine error
```

#### 修復 1.2：celery_app.py - 恢復檔案

**檔案：** `src/infrastructure/celery_app.py`

**問題：** 檔案在第 6-37 行截斷

**解決方案：** 從 git 歷史恢復
```bash
cd ~/Work/Projects/AI/investment-advisor
git checkout HEAD~1 -- src/infrastructure/celery_app.py
# OR manually reconstruct from backup if needed
```

**驗證：**
```bash
python -c "from src.infrastructure.celery_app import app; print('OK')"
```

### Phase 2：Issue #4 修復 (3-4 小時)

#### 修復 2.1：dashboard_service.py - NLV/P&L 計算

**檔案：** `src/services/dashboard_service.py`

```python
# ❌ BEFORE (Lines 50-115)
def get_portfolio_nlv():
    # Incorrectly adds uninvested cash to equity
    return portfolio_value + cash_balance

def get_portfolio_pnl():
    # Wrong formula: should be position P&L, not this
    return current_nlv - invested_capital

# ✅ AFTER
def get_portfolio_nlv():
    # Use eToro authoritative value
    account = etoro_service.get_account()
    return account.total_equity  # $1,105.33 (matches eToro)

def get_portfolio_pnl():
    # Sum all position P&L (realized + unrealized)
    positions = portfolio_repo.get_all_positions()
    return sum(p.unrealized_pnl + p.realized_pnl for p in positions)
```

#### 修復 2.2：analytics_service.py - 移除本地計算

**檔案：** `src/services/analytics_service.py` (Lines 62-74)

```python
# ❌ BEFORE
def calculate_portfolio_metrics():
    local_nlv = sum_position_values() + uninvested_cash
    
# ✅ AFTER
def calculate_portfolio_metrics():
    # Use eToro as single source of truth
    account = etoro_service.get_account()
    nlv = account.total_equity
    last_fetch = datetime.now(timezone.utc)
```

#### 修復 2.3：etoro_service.py - 添加同步戳記

```python
class EToroService:
    def get_account(self):
        account = self.client.get_account()
        account.last_fetched_at = datetime.now(timezone.utc)
        cache_sync_timestamp(account.last_fetched_at)  # ← NEW
        return account
```

---

## 📋 驗證清單

### Phase 1 驗收標準（修復後立即驗證）

- [ ] `job_etoro_sync()` 執行無 coroutine 錯誤
- [ ] Scheduler 日誌顯示 ✅ PASSED (而非 FAILED)
- [ ] 下一個 4h 週期任務成功執行

**預期結果：** 排程日誌顯示 `PASSED` (而非每次 FAILED)

```bash
# Run verification
python -m pytest tests/unit/services/test_scheduler_service.py -v
# Expected: 8/8 PASSED
```

### Phase 2 驗收標準（修復後）

- [ ] `get_portfolio_nlv()` = $1,105.33（匹配 eToro）
- [ ] `get_portfolio_pnl()` = $314.64（匹配 eToro）
- [ ] Dashboard 顯示 `last_portfolio_fetch_time` 
- [ ] 3 次連續查詢 NLV 值相同（無波動）

**驗證指令：**
```bash
cd ~/Work/Projects/AI/investment-advisor

# Test NLV/P&L calculations
python -m pytest tests/unit/services/test_dashboard_service.py -v -k "nlv or pnl"
# Expected: All PASSED with eToro values

# Test data sync
python -m pytest tests/unit/integrations/test_etoro_sync.py -v
# Expected: 5/5 PASSED, timestamps present
```

---

## 📊 影響評估

### Issue #5 修復後
- ✅ 排程任務恢復正常
- ✅ 自動 Broker 同步每 4h 執行一次
- ✅ Portfolio 數據實時更新
- **預期收益：** 自動化交易恢復 | 數據新鮮度 < 5 分鐘

### Issue #4 修復後
- ✅ Dashboard NLV 匹配 eToro ($1,105.33)
- ✅ Dashboard P&L 匹配 eToro ($314.64)
- ✅ 審計追蹤：最後同步時間可追蹤
- ✅ 用戶信任度恢復
- **預期收益：** 消除 +$1,100 虛報 | 完全數據可溯源

---

## 🚀 實施時間表

| 階段 | 任務 | 預計時間 | 依賴 |
|------|------|---------|------|
| 1.1 | 修復 scheduler_service.py async | 10 min | 無 |
| 1.2 | 恢復 celery_app.py | 5 min | 無 |
| ✅ | **Phase 1 驗收** | 10 min | 1.1 + 1.2 |
| 2.1 | 修復 dashboard_service.py NLV/P&L | 1.5h | Phase 1 ✅ |
| 2.2 | 修復 analytics_service.py | 1h | Phase 1 ✅ |
| 2.3 | 添加同步戳記 | 1h | Phase 1 ✅ |
| ✅ | **Phase 2 驗收** | 0.5h | 2.1+2.2+2.3 |
| 🎉 | **全部完成** | **5.5 小時** | |

---

## ⚠️ 風險與注意事項

### 數據保護 🔒

- **NO BREAKING CHANGES：** 所有修復都是非破壞性
- **DB 完全保留：** 無遷移、無刪除、無重置
- ✅ 驗證：舊數據持續存儲 + 新計算使用 eToro 值
- ✅ 回滾方案：Git revert (如需要)

### 部署安全性 🛡️

1. **先修復 Issue #5**（排程才能自動同步新數據）
2. **再修復 Issue #4**（計算邏輯修正）
3. **驗證階段** — 所有 pytest 必須 PASSED
4. **監控 24h** — 確認無回歸

---

## 📁 相關檔案

**由 subagent 生成的詳細分析：**
- ✅ `ISSUE_4_ROOT_CAUSE_ANALYSIS.md` (14 KB) — 詳細計算流程
- ✅ `ISSUE_4_FIX_IMPLEMENTATION.md` (18 KB) — 完整程式碼修改
- ✅ `ISSUE_5_ROOT_CAUSE_ANALYSIS.md` (15 KB) — 排程系統分析
- ✅ `ISSUE_5_INVESTIGATION_SUMMARY.txt` — 快速參考

---

## ✅ 後續步驟

1. **立即執行 Phase 1** (20 分鐘)
   - 修復 scheduler async/await
   - 恢復 celery_app.py
   - 驗證排程恢復

2. **執行 Phase 2** (3-4 小時)
   - 應用計算修正
   - 驗證 NLV/P&L 匹配 eToro
   - 監控同步戳記

3. **部署** 
   - 監控 24 小時
   - 確認無數據回歸
   - 向用戶通知修復完成

---

**狀態：準備就緒 → 等待執行授權** 🎯

您要現在開始 Phase 1 嗎？(Estimated: 20 分鐘)
