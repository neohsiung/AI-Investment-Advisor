import streamlit as st
import json
from src.services.settings_service import SettingsService

def render_data_sources_tab(st, settings_service, user_id):
    """
    Renders the Data Source Management tab.
    數據源管理分頁：提供 15+ 資料源的開關與參數設定。
    """
    st.header("數據源矩陣管理 (Data Source Matrix)")
    st.markdown("---")

    # Define Source Groups by Coverage/Priority
    source_groups = {
        "總體經濟 (Macro - P0)": {
            "priority": 1,
            "sources": [
                {
                    "id": "fred",
                    "name": "FRED (Federal Reserve)",
                    "desc": "聯準會官方經濟數據 (利率, CPI, 失業率)。系統監控宏觀體制的基石。",
                    "fields": {
                        "api_key": {"label": "API Key", "type": "password", "help": "在 St. Louis Fed 官網獲取。"}
                    }
                },
                {
                    "id": "alpha_vantage",
                    "name": "Alpha Vantage",
                    "desc": "提供總經指標、外匯與情感分數。補足 MacroAgent 的多維度指標。",
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
                    "fields": {
                        "ip": {"label": "OpenD IP", "default": "127.0.0.1"},
                        "port": {"label": "OpenD Port", "default": "11111"}
                    }
                },
                {
                    "id": "polygon",
                    "name": "Polygon.io",
                    "desc": "美股期權與盤中逐筆成交數據。適合 Sentinel 即時攔截。",
                    "fields": {
                        "api_key": {"label": "API Key", "type": "password"}
                    }
                },
                {
                    "id": "alpaca",
                    "name": "Alpaca Markets",
                    "desc": "API-First 零佣金交易平台。適合自動化策略執行。",
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
                    "fields": {
                        "api_key": {"label": "API Key", "type": "password"}
                    }
                },
                {
                    "id": "yahoo_finance",
                    "name": "Yahoo Finance (yfinance)",
                    "desc": "穩定且免 Key 的歷史數據源。用於回測數據填充。",
                    "fields": {} # yfinance does not need key
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
                    "fields": {
                        "api_key": {"label": "API Key", "type": "password"}
                    }
                },
                {
                    "id": "tiingo",
                    "name": "Tiingo",
                    "desc": "內容乾淨且具備標籤化 (Tagging) 的新聞流。",
                    "fields": {
                        "api_key": {"label": "API Key", "type": "password"}
                    }
                },
                {
                    "id": "news_api",
                    "name": "NewsAPI.org",
                    "desc": "全球新聞廣度掃描。",
                    "fields": {
                        "api_key": {"label": "API Key", "type": "password"}
                    }
                },
                {
                    "id": "tavily",
                    "name": "Tavily Search",
                    "desc": "專為 AI 設計的金融搜尋引擎。用於 Breaking News 趨勢掃描。",
                    "fields": {
                        "api_key": {"label": "API Key", "type": "password"}
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
                    "fields": {
                        "api_key": {"label": "API Key", "type": "password"}
                    }
                },
                {
                    "id": "whale_alert",
                    "name": "Whale Alert",
                    "desc": "監控鏈上大鯨魚異動。預警拋售與風險。",
                    "fields": {
                        "api_key": {"label": "API Key", "type": "password"}
                    }
                },
                {
                    "id": "glassnode",
                    "name": "Glassnode",
                    "desc": "鏈上宏觀指標。用於判斷牛熊週期。",
                    "fields": {
                        "api_key": {"label": "API Key", "type": "password"}
                    }
                },
                {
                    "id": "alternative_me",
                    "name": "Fear & Greed Index",
                    "desc": "市場恐懼與貪婪指數。調節風險權重的關鍵訊號。",
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
                    "fields": {"secret": {"label": "Webhook Secret", "type": "password", "help": "用於 URL 參數驗證"}}
                },
                {
                    "id": "webhook_zapier_sec",
                    "name": "2. Zapier (SEC EDGAR)",
                    "desc": "攔截 SEC 官網 10-K/10-Q 最新財報提交。",
                    "fields": {"secret": {"label": "Webhook Secret", "type": "password"}}
                },
                {
                    "id": "webhook_make_social",
                    "name": "3. Make.com (X / Reddit)",
                    "desc": "關鍵意見領袖推文或社群聲量爆發展發 Webhook。",
                    "fields": {"secret": {"label": "Webhook Secret", "type": "password"}}
                },
                {
                    "id": "webhook_finnhub",
                    "name": "4. Finnhub Webhooks",
                    "desc": "即時財報預期落差 (Earnings Surprises)。",
                    "fields": {"secret": {"label": "Webhook Secret", "type": "password"}}
                },
                {
                    "id": "webhook_polygon",
                    "name": "5. Polygon.io Webhooks",
                    "desc": "市場停牌 (Halts) 與異常期權 (Options Sweeps) 事件。",
                    "fields": {"secret": {"label": "Webhook Secret", "type": "password"}}
                },
                {
                    "id": "webhook_macro",
                    "name": "6. Macro Calendar (Zapier)",
                    "desc": "CPI / FOMC 總經數據發布時即時觸發。",
                    "fields": {"secret": {"label": "Webhook Secret", "type": "password"}}
                },
                {
                    "id": "webhook_github",
                    "name": "7. GitHub Ops",
                    "desc": "策略代碼庫更新或 Issue 觸發 Vibe Coding Agent。",
                    "fields": {"secret": {"label": "Webhook Secret", "type": "password"}}
                },
                {
                    "id": "webhook_sentry",
                    "name": "8. Sentry Alerts",
                    "desc": "投資顧問系統或資料管線異常攔截。",
                    "fields": {"secret": {"label": "Webhook Secret", "type": "password"}}
                },
                {
                    "id": "webhook_typeform",
                    "name": "9. Typeform (KYC)",
                    "desc": "新客戶風險評估填寫完畢事件。",
                    "fields": {"secret": {"label": "Webhook Secret", "type": "password"}}
                },
                {
                    "id": "webhook_ifttt",
                    "name": "10. IFTTT (Broker Email)",
                    "desc": "攔截未提供 API 之券商 PDF 報告轉發觸發。",
                    "fields": {"secret": {"label": "Webhook Secret", "type": "password"}}
                }
            ]
        }
    }

    # Load all settings once
    settings = settings_service.get_all_settings()

    # Iterate through groups with collapsibles
    for group_name, group_data in source_groups.items():
        with st.expander(f"📁 {group_name}", expanded=(group_data['priority'] <= 2)):
            for source in group_data['sources']:
                sid = source['id']
                col1, col2 = st.columns([1, 4])
                
                with col1:
                    # Toggle Enable/Disable
                    is_enabled = st.toggle(
                        "啟用", 
                        key=f"enabled_{sid}", 
                        value=settings.get(f"source_{sid}_enabled", "false") == "true",
                        help=f"是否開啟 {source['name']} 的自動輪詢或監控"
                    )
                
                with col2:
                    st.write(f"**{source['name']}**")
                    st.caption(source['desc'])
                
                # If enabled, show config fields
                if is_enabled:
                    scol1, scol2 = st.columns([1, 1])
                    for i, (fname, fmeta) in enumerate(source['fields'].items()):
                        key = f"source_{sid}_{fname}"
                        val = settings.get(key, fmeta.get('default', ""))
                        
                        target_col = scol1 if i % 2 == 0 else scol2
                        with target_col:
                            if fmeta.get('type') == 'password':
                                new_val = st.text_input(fmeta['label'], value=val, type="password", key=f"input_{key}", help=fmeta.get('help', ""))
                            else:
                                new_val = st.text_input(fmeta['label'], value=val, key=f"input_{key}", help=fmeta.get('help', ""))
                            
                            if new_val != val:
                                settings_service.save_setting(key, new_val)
                
                # Save toggle state if changed
                toggle_str = "true" if is_enabled else "false"
                if toggle_str != settings.get(f"source_{sid}_enabled", "false"):
                    settings_service.save_setting(f"source_{sid}_enabled", toggle_str)
                
                st.divider()

    st.success("數據源設定已即時同步至資料庫。")
