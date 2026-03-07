"""
Centralized Configuration for the Data Source Matrix.
統一數據源矩陣設定，作為 Frontend UI 與 Backend (Sentinel) Polling 邏輯的唯一真實來源 (Source of Truth)。
"""
from typing import List, Dict, Any, Optional

DATA_SOURCE_GROUPS = {
    "總體經濟 (Macro - P0)": {
        "priority": 1,
        "sources": [
            {
                "id": "fred",
                "name": "FRED (Federal Reserve)",
                "desc": "聯準會官方經濟數據 (利率, CPI, 失業率)。系統監控宏觀體制的基石。",
                "trigger_type": "polling",
                "fields": {
                    "api_key": {"label": "API Key", "type": "password", "help": "在 St. Louis Fed 官網獲取。"}
                }
            },
            {
                "id": "alpha_vantage",
                "name": "Alpha Vantage",
                "desc": "提供總經指標、外匯與情感分數。補足 MacroAgent 的多維度指標。",
                "trigger_type": "polling",
                "fields": {
                    "api_key": {"label": "API Key", "type": "password"}
                }
            }
        ]
    },
    "市場行情與實盤傳輸 (Market & Execution - P1)": {
        "priority": 2,
        "sources": [
            {
                "id": "futu",
                "name": "Futu OpenAPI (富途)",
                "desc": "專業港美股報價與實盤交易。需運行本地 OpenD 網關。",
                "trigger_type": "live",
                "fields": {
                    "ip": {"label": "OpenD IP", "default": "127.0.0.1"},
                    "port": {"label": "OpenD Port", "default": "11111"}
                }
            },
            {
                "id": "polygon",
                "name": "Polygon.io",
                "desc": "美股期權與盤中逐筆成交數據。適合 Sentinel 即時攔截。",
                "trigger_type": "polling",
                "fields": {
                    "api_key": {"label": "API Key", "type": "password"}
                }
            },
            {
                "id": "alpaca",
                "name": "Alpaca Markets",
                "desc": "API-First 零佣金交易平台。適合自動化策略執行。",
                "trigger_type": "live",
                "fields": {
                    "key_id": {"label": "API Key ID", "type": "password"},
                    "secret_key": {"label": "Secret Key", "type": "password"}
                }
            }
        ]
    },
    "財報與個股基本面 (Fundamental - P0)": {
        "priority": 3,
        "sources": [
            {
                "id": "fmp",
                "name": "FMP (Financial Modeling Prep)",
                "desc": "高精度全球財報數據與 DCF 模型。Fundamental Swarm 的燃料。",
                "trigger_type": "polling",
                "fields": {
                    "api_key": {"label": "API Key", "type": "password"}
                }
            },
            {
                "id": "yahoo_finance",
                "name": "Yahoo Finance (yfinance)",
                "desc": "穩定且免 Key 的歷史數據源。用於回測數據填充。",
                "trigger_type": "polling",
                "fields": {} 
            }
        ]
    },
    "情感與即時新聞 (Sentiment & News - P2)": {
        "priority": 4,
        "sources": [
            {
                "id": "finnhub",
                "name": "Finnhub",
                "desc": "AI 情緒分數與新聞聚合。Generous free tier。",
                "trigger_type": "polling",
                "fields": {
                    "api_key": {"label": "API Key", "type": "password"}
                }
            },
            {
                "id": "tiingo",
                "name": "Tiingo",
                "desc": "內容乾淨且具備標籤化 (Tagging) 的新聞流。",
                "trigger_type": "polling",
                "fields": {
                    "api_key": {"label": "API Key", "type": "password"}
                }
            },
            {
                "id": "news_api",
                "name": "NewsAPI.org",
                "desc": "全球新聞廣度掃描。",
                "trigger_type": "polling",
                "fields": {
                    "api_key": {"label": "API Key", "type": "password"}
                }
            },
            {
                "id": "tavily",
                "name": "Tavily Search",
                "desc": "專為 AI 設計的金融搜尋引擎。用於 Breaking News 趨勢掃描。",
                "trigger_type": "polling",
                "fields": {
                    "api_key": {"label": "API Key", "type": "password"}
                }
            },
            {
                "id": "readwise",
                "name": "Readwise Highlights",
                "desc": "自動同步並以 AI 篩選你畫線的投資筆記，匯入 Sentinel 監控迴圈。",
                "trigger_type": "polling",
                "fields": {
                    "api_key": {"label": "API Key", "type": "password", "help": "可在 readwise.io/access_token 取得"}
                }
            }
        ]
    },
    "加密貨幣與鏈上監控 (Crypto & On-chain)": {
        "priority": 5,
        "sources": [
            {
                "id": "cryptopanic",
                "name": "CryptoPanic",
                "desc": "幣圈情緒聚合指標。偵測市場爆發性事件。",
                "trigger_type": "polling",
                "fields": {
                    "api_key": {"label": "API Key", "type": "password"}
                }
            },
            {
                "id": "whale_alert",
                "name": "Whale Alert",
                "desc": "監控鏈上大鯨魚異動。預警拋售與風險。",
                "trigger_type": "polling",
                "fields": {
                    "api_key": {"label": "API Key", "type": "password"}
                }
            },
            {
                "id": "glassnode",
                "name": "Glassnode",
                "desc": "鏈上宏觀指標。用於判斷牛熊週期。",
                "trigger_type": "polling",
                "fields": {
                    "api_key": {"label": "API Key", "type": "password"}
                }
            },
            {
                "id": "alternative_me",
                "name": "Fear & Greed Index",
                "desc": "市場恐懼與貪婪指數。調節風險權重的關鍵訊號。",
                "trigger_type": "polling",
                "fields": {}
            }
        ]
    },
    "事件驅動 Webhook 觸發源 (Event-Driven Triggers)": {
        "priority": 6,
        "sources": [
            {
                "id": "webhook_tradingview",
                "name": "1. TradingView Alerts",
                "desc": "接收專屬技術指標或價格突破 Webhook。",
                "trigger_type": "webhook",
                "fields": {"secret": {"label": "Webhook Secret", "type": "password", "help": "用於 URL 參數驗證"}}
            },
            {
                "id": "webhook_zapier_sec",
                "name": "2. Zapier (SEC EDGAR)",
                "desc": "攔截 SEC 官網 10-K/10-Q 最新財報提交。",
                "trigger_type": "webhook",
                "fields": {"secret": {"label": "Webhook Secret", "type": "password"}}
            },
            {
                "id": "webhook_make_social",
                "name": "3. Make.com (X / Reddit)",
                "desc": "關鍵意見領袖推文或社群聲量爆發展發 Webhook。",
                "trigger_type": "webhook",
                "fields": {"secret": {"label": "Webhook Secret", "type": "password"}}
            },
            {
                "id": "webhook_finnhub",
                "name": "4. Finnhub Webhooks",
                "desc": "即時財報預期落差 (Earnings Surprises)。",
                "trigger_type": "webhook",
                "fields": {"secret": {"label": "Webhook Secret", "type": "password"}}
            },
            {
                "id": "webhook_macro",
                "name": "6. Macro Calendar (Zapier)",
                "desc": "CPI / FOMC 總經數據發布時即時觸發。",
                "trigger_type": "webhook",
                "fields": {"secret": {"label": "Webhook Secret", "type": "password"}}
            },
            {
                "id": "webhook_github",
                "name": "7. GitHub Ops",
                "desc": "策略代碼庫更新或 Issue 觸發 Vibe Coding Agent。",
                "trigger_type": "webhook",
                "fields": {"secret": {"label": "Webhook Secret", "type": "password"}}
            },
            {
                "id": "webhook_sentry",
                "name": "8. Sentry Alerts",
                "desc": "投資顧問系統或資料管線異常攔截。",
                "trigger_type": "webhook",
                "fields": {"secret": {"label": "Webhook Secret", "type": "password"}}
            },
            {
                "id": "webhook_typeform",
                "name": "9. Typeform (KYC)",
                "desc": "新客戶風險評估填寫完畢事件。",
                "trigger_type": "webhook",
                "fields": {"secret": {"label": "Webhook Secret", "type": "password"}}
            },
            {
                "id": "webhook_ifttt",
                "name": "10. IFTTT (Broker Email)",
                "desc": "攔截未提供 API 之券商 PDF 報告轉發觸發。",
                "trigger_type": "webhook",
                "fields": {"secret": {"label": "Webhook Secret", "type": "password"}}
            }
        ]
    }
}

def get_pollable_sources() -> List[str]:
    """
    Returns a list of source IDs that should be actively polled by Sentinel.
    """
    pollable = []
    for group in DATA_SOURCE_GROUPS.values():
        for source in group["sources"]:
            if source.get("trigger_type") == "polling":
                pollable.append(source["id"])
    return pollable

def get_webhook_sources() -> List[str]:
    """
    Returns a list of source IDs that operate via webhooks.
    """
    webhooks = []
    for group in DATA_SOURCE_GROUPS.values():
        for source in group["sources"]:
            if source.get("trigger_type") == "webhook":
                webhooks.append(source["id"])
    return webhooks

def get_source_schema(source_id: str) -> Optional[Dict[str, Any]]:
    """
    Returns the schema definition for a given source_id.
    """
    for group in DATA_SOURCE_GROUPS.values():
        for source in group["sources"]:
            if source["id"] == source_id:
                return source
    return None
