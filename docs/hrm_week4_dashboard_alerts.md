# HRM Week 4: 成本儀表板 + 告警系統

**日期**: 2026-04-27T23:44:59.351878

## 🌐 Backend API

| 方法 | 端點 | 描述 |
|------|------|------|
| GET | /api/v1/costs/summary | 成本摘要 (week/month) |
| GET | /api/v1/costs/by-tier | 按層級成本分佈 |
| GET | /api/v1/costs/by-provider | 按提供商成本分佈 |
| GET | /api/v1/costs/budget-status | 預算狀態 (週/月) |
| GET | /api/v1/costs/trending | 成本趨勢 (可配置天數) |
| GET | /api/v1/costs/model-performance | 模型性能對比 |

## 🚨 告警系統

| 閾值 | 說明 |
|------|------|
| 70% | ⚠️ Warning - Monitor spending |
| 85% | 🚨 Alert - Consider cost optimization |
| 100% | 🆘 Critical - Hard limit enforced, switch to free models |

## 📊 儀表板組件

- **Budget Status Card**: Weekly/Monthly budget, Current spend, Remaining, Status indicator
- **Cost by Tier Pie Chart**: Cost distribution by cognitive tier
- **Cost by Provider Bar Chart**: Cost distribution by model provider
- **Cost Trending Line Chart**: 30-day cost and request trend
- **Model Performance Table**: Usage count, Quality score, Success rate, Latency, Cost/request
