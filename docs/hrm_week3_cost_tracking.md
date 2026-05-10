# HRM Week 3: Per-User 成本追蹤 DB 集成

**日期**: 2026-04-27T23:44:07.366341

## 📊 數據庫設計

### user_budgets

用戶預算追蹤與配置

**列**:
- user_id (PK)
- monthly_budget_usd
- weekly_budget_usd
- current_week_spent_usd
- current_month_spent_usd
- ... 及其他 3 列

**索引**: idx_user_id

### request_costs

每個請求的成本記錄

**列**:
- id (PK)
- user_id (FK)
- request_id
- tier
- model_provider
- ... 及其他 8 列

**索引**: idx_user_id, idx_request_id, idx_created_at, idx_tier

### cost_review_logs

週期性審查日誌

**列**:
- id (PK)
- user_id (FK)
- review_week
- review_year
- total_requests
- ... 及其他 5 列

**索引**: idx_user_id, idx_review_week

### model_performance_metrics

模型性能指標追蹤

**列**:
- model_provider
- model_name
- tier
- request_count
- success_count
- ... 及其他 3 列

**索引**: idx_provider_model, idx_tier

## ⚙️ 工作流

### Per-Request Flow

1. SettingsAwareModelRouter 路由請求
2. 執行模型推理
3. PerUserCostTracker.record_request_cost() 記錄成本
4. 更新 user_budgets 當週/當月花費
5. 檢查預算告警 (70%, 85%, 100%)
6. 如觸發硬限制，後續限制付費模型

