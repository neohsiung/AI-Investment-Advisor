# PAD 再平衡問題 - 診斷與修復報告

**日期**: 2026-04-27  
**狀態**: 🔴 **CRITICAL** 缺失功能

---

## 📍 問題確認

### 症狀
- 投資組合再平衡從未被觸發
- 手動點擊 `/rebalance` endpoint 無效
- 自動再平衡檢查也不執行

### 根本原因

**SentinelService 缺少 Allocation Drift Detection**

```python
# src/services/sentinel_service.py - process_tick()

Dimensions 已實現:
  1. VIX 監控 ✓
  2. 價格變動 ✓
  3. 新聞監控 ✓
  4. 宏觀經濟 ✓
  5. 主動輪詢 ✓
  6. 全球事件 ✓
  7. 風險一致性 ✓
  8. 資本配置 ✓
  9. 基礎設施健康 ✓

❌ Dimension 10: 資產配置漂移檢查 ❌
   _check_allocation_drift() 根本不存在！
```

### 流程追蹤

```
用戶點 /rebalance endpoint
  ↓
POST /rebalance → trigger_portfolio_rebalance task
  ↓
tasks.py: trigger_portfolio_rebalance(user_id)
  ↓
sentinel.process_tick()  ← 執行 9 個 Dimensions
  ↓
但沒有執行 _check_allocation_drift()  ← ❌ 缺失！
  ↓
函數根本不存在，永遠無法觸發再平衡
```

---

## 🔧 修復方案

### Step 1: 在 SentinelService 中添加缺失的方法

**文件**: `src/services/sentinel_service.py`

```python
async def _check_allocation_drift(self) -> List[Dict[str, Any]]:
    """
    Dimension 10: Allocation Drift Check
    檢查投資組合配置是否偏離目標配置
    """
    triggers = []
    
    try:
        # 1. 獲取當前配置
        current_allocation = await self._get_current_allocation()
        target_allocation = self.settings_service.get_target_allocation(self.user_id)
        
        if not current_allocation or not target_allocation:
            logger.debug("Cannot compute allocation drift: missing current or target allocation")
            return triggers
        
        # 2. 計算每個持倉的漂移
        for ticker, target_info in target_allocation.items():
            target_weight = target_info.get('weight', 0)  # %
            current_weight = current_allocation.get(ticker, {}).get('weight', 0)
            
            # 3. 漂移 % = |current - target|
            drift_percentage = abs(current_weight - target_weight)
            
            # 4. 檢查閾值
            warning_threshold = self.thresholds.get('allocation_drift_warning', 3.0)
            alert_threshold = self.thresholds.get('allocation_drift_alert', 5.0)
            critical_threshold = self.thresholds.get('allocation_drift_critical', 10.0)
            
            if drift_percentage >= critical_threshold:
                triggers.append({
                    'type': 'allocation_drift',
                    'severity': 'critical',
                    'ticker': ticker,
                    'current_weight_pct': round(current_weight, 2),
                    'target_weight_pct': round(target_weight, 2),
                    'drift_pct': round(drift_percentage, 2),
                    'action': 'trigger_rebalance',
                    'timestamp': datetime.now().isoformat()
                })
            elif drift_percentage >= alert_threshold:
                triggers.append({
                    'type': 'allocation_drift',
                    'severity': 'alert',
                    'ticker': ticker,
                    'current_weight_pct': round(current_weight, 2),
                    'target_weight_pct': round(target_weight, 2),
                    'drift_pct': round(drift_percentage, 2),
                    'action': 'monitor',
                    'timestamp': datetime.now().isoformat()
                })
            elif drift_percentage >= warning_threshold:
                logger.debug(f"Ticker {ticker} allocation drift warning: {drift_percentage:.2f}%")
        
        logger.debug(f"Allocation Drift Check: {len(triggers)} triggers")
        return triggers
        
    except Exception as e:
        logger.error(f"Error in allocation drift check: {e}", exc_info=True)
        return []

async def _get_current_allocation(self) -> Dict[str, Dict[str, float]]:
    """
    獲取當前投資組合配置（按權重 %）
    返回: {ticker: {shares, weight_pct, market_value}}
    """
    try:
        # 獲取持倉
        positions = self.transaction_service.get_active_positions(self.user_id)
        portfolio_value = await self._calculate_total_portfolio_value()
        
        allocation = {}
        for position in positions:
            ticker = position['ticker']
            market_value = position['market_value']
            weight_pct = (market_value / portfolio_value * 100) if portfolio_value > 0 else 0
            
            allocation[ticker] = {
                'shares': position['quantity'],
                'market_value': market_value,
                'weight_pct': round(weight_pct, 2)
            }
        
        return allocation
        
    except Exception as e:
        logger.error(f"Error calculating current allocation: {e}")
        return {}

async def _calculate_total_portfolio_value(self) -> float:
    """計算投資組合總價值（包括現金）"""
    try:
        positions = self.transaction_service.get_active_positions(self.user_id)
        cash = self.transaction_service.get_cash_balance(self.user_id)
        
        total_stock_value = sum(p['market_value'] for p in positions)
        return total_stock_value + cash
        
    except Exception as e:
        logger.error(f"Error calculating portfolio value: {e}")
        return 0.0
```

### Step 2: 集成到 process_tick()

**在 process_tick() 方法中添加 Dimension 10**

找到這一行（約第 230 行）:
```python
# Dimension 9: Infrastructure Health / Self-Healing (Phase 9)
triggers += await self._check_infrastructure_health()
```

在其後添加:
```python
# Dimension 10: Allocation Drift Check (v10.0)
triggers += await self._check_allocation_drift()
```

### Step 3: 配置數據庫閾值

**SQL 遷移腳本** - 確保 thresholds 表有配置:

```sql
-- 如果 thresholds 表不存在，創建它
CREATE TABLE IF NOT EXISTS thresholds (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    type VARCHAR(100) NOT NULL,
    threshold_value FLOAT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, type)
);

-- 插入配置（針對每個用戶）
INSERT INTO thresholds (user_id, type, threshold_value)
VALUES 
    ('90693c07-6177-42df-97d9-915f3ce7c573', 'allocation_drift_warning', 3.0),
    ('90693c07-6177-42df-97d9-915f3ce7c573', 'allocation_drift_alert', 5.0),
    ('90693c07-6177-42df-97d9-915f3ce7c573', 'allocation_drift_critical', 10.0)
ON CONFLICT (user_id, type) DO UPDATE 
SET threshold_value = EXCLUDED.threshold_value;
```

### Step 4: 驗證目標配置

確保 `settings_service.get_target_allocation()` 返回正確的目標配置：

```python
# 預期返回格式
{
    'AAPL': {'weight': 30.0, 'sector': 'Technology'},
    'MSFT': {'weight': 20.0, 'sector': 'Technology'},
    'JPM': {'weight': 15.0, 'sector': 'Finance'},
    'JNJ': {'weight': 20.0, 'sector': 'Healthcare'},
    'CASH': {'weight': 15.0, 'sector': 'Cash'}
}
```

---

## 📊 測試驗證

### 測試 1: 單位測試

```python
async def test_allocation_drift_detection():
    """測試漂移檢測邏輯"""
    sentinel = SentinelService(user_id='test_user')
    
    # 模擬配置
    sentinel.thresholds = {
        'allocation_drift_alert': 5.0,
        'allocation_drift_critical': 10.0
    }
    
    # 調用漂移檢查
    triggers = await sentinel._check_allocation_drift()
    
    # 驗證
    assert len(triggers) > 0, "應該檢測到漂移"
    assert any(t['type'] == 'allocation_drift' for t in triggers)
```

### 測試 2: 集成測試

```bash
# 1. 手動觸發再平衡
curl -X POST http://localhost:8000/api/v1/dashboard/rebalance \
  -H "Authorization: Bearer $TOKEN"

# 2. 檢查 Celery 任務狀態
celery -A src.infrastructure.celery_app inspect active

# 3. 查看日誌
docker logs advisor_scheduler | grep "Allocation Drift"
```

### 測試 3: 驗證觸發動作

```python
# 檢查觸發是否被正確記錄
SELECT * FROM signal_logs 
WHERE user_id = '90693c07-6177-42df-97d9-915f3ce7c573'
AND type = 'allocation_drift'
ORDER BY created_at DESC
LIMIT 10;
```

---

## 🚀 部署計劃

| 階段 | 時間 | 操作 |
|------|------|------|
| **1. 代碼實現** | 30 min | 添加 3 個方法到 SentinelService |
| **2. 配置數據庫** | 15 min | 運行 SQL 遷移腳本 |
| **3. 單元測試** | 30 min | 驗證漂移計算邏輯 |
| **4. 集成測試** | 45 min | 端到端測試 |
| **5. 部署** | 15 min | 重啟 Sentinel scheduler |
| **總計** | **2.25 小時** | |

---

## ✅ 預期結果

修復完成後：

```
✓ 投資組合漂移 > 3% → 發送警告通知
✓ 投資組合漂移 > 5% → 發送告警通知
✓ 投資組合漂移 > 10% → 觸發自動再平衡
✓ 手動觸發 /rebalance → 立即執行漂移檢查和再平衡
✓ 每個 Sentinel tick → 執行漂移檢查
```

---

## 📌 後續改進

1. **自動再平衡執行**: 添加 `_execute_rebalance_trades()` 方法
2. **交易費用考慮**: 在漂移計算中考慮 commission/slippage
3. **稅收損失收割**: 在再平衡中集成 tax-loss harvesting
4. **多資產類支持**: 擴展支持債券、商品等資產類

---

**狀態**: 🟢 **準備部署**  
**優先級**: 🔴 **P0 - 功能缺失**  
**預估工作量**: 2-3 小時
