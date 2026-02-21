---
description: Observability, Tracing, and Notification Standards (OTel + SigNoz)
---

# 系統觀測與通知架構規範 (Observability & Notification Standards)

遵守以下事項：

1. **遙測資料標準化 (OpenTelemetry Standard)**：
   所有微服務必須透過 OpenTelemetry (OTel) 進行遙測打點。
   * 必須使用 `python-json-logger` 進行結構化日誌輸出 (Structured Logging)，確保每一筆 log 都可被容易地索引與解析。
   * 全域 Tracing (Trace ID / Span ID) 必須於 HTTP / gRPC 邊界進行透傳 (Context Propagation)。

2. **自託管監控優先 (Self-Hosted Backend First)**：
   * 遙測數據 (Metrics, Traces, Logs) 統一經由 `OTEL_EXPORTER_OTLP_ENDPOINT` 輸出至本地端 SigNoz 平台。
   * 原則上禁止隨意將遙測資料寫入未受控的第三方 SaaS，必須保證機敏資料不出網。

3. **統一通知匯流排 (Unified Notification Bus)**：
   * 嚴禁各個獨立服務 (如 Scheduler, Sentinel, Dashboard) 自行實作 SMTP 或 LINE API 的直接呼叫。
   * 所有的通知 (包含 Email 報告與 LINE 告警) 必須轉換為標準的 JSON Payload，透過 HTTP POST 發送至獨立的 **Standalone Notification Microservice**。
   * 該 Notification Service 負責進行通知的排隊 (Queue)、去重 (Deduplication) 以及分發 (Dispatching)。

4. **服務解耦 (Microservice Isolation)**：
   * 在使用 Notification Service 或外部 API 時，主程式必須實作非同步 (Async) 防呆與超時保護 (Timeout handling)，確保外部服務癱瘓時，不會阻塞核心交易與排程。
