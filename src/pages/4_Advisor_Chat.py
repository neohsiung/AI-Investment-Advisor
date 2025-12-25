import streamlit as st
import pandas as pd
import time
import sys
import os

# Ensure project root is in sys.path
sys.path.append(os.getcwd())

from src.agents.factory import AgentFactory
from src.market_data import MarketDataService
from src.utils.logger import setup_logger
from src.utils.ui import load_custom_css

logger = setup_logger("Page_Chat")

# Load Custom Global CSS
load_custom_css()

st.set_page_config(page_title="AI Advisor Chat", page_icon="💬", layout="wide")

st.title("💬 AI 投資顧問 (Interactive Advisor)")
st.info("ℹ️ 此對話為即時諮詢模式，內容僅供當下參考，**不會**存入系統的正式週報/月報資料庫，亦不影響例行性績效追蹤。")

if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Input
if prompt := st.chat_input("請問關於投資的問題 (例如: AAPL 現在可以買嗎? / 分析 TSLA 基本面)"):
    # Add user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Bot Logic
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        full_response = ""
        
        with st.status("思考與調度中 (Dispatching)...") as status:
            try:
                # 1. Dispatch
                dispatcher = AgentFactory.create_agent("Dispatcher")
                dispatch_result = dispatcher.run({"user_input": prompt})
                
                agents_to_call = dispatch_result.get("agents", [])
                tickers = dispatch_result.get("tickers", [])
                reason = dispatch_result.get("reason", "Analysis required.")
                
                status.write(f"**意圖識別**: {dispatch_result.get('intent', 'unknown')}")
                status.write(f"**思考路徑**: {reason}")
                status.write(f"**涉及代碼**: {tickers} | **調用專家**: {agents_to_call}")
                logger.info(f"Dispatch: {dispatch_result}")
                
                results = {}
                market_service = MarketDataService()
                
                # 2. Parallel Execution (Simulated sequential here for simplicity)
                context_texts = []
                
                if "Macro" in agents_to_call:
                    status.write("🔄 **Macro Agent**: 正在搜集總體經濟數據 (GDP, CPI, VIX)...")
                    macro_agent = AgentFactory.create_macro_agent()
                    # Need real data
                    from src.services.fred_service import FredService
                    fred = FredService()
                    fred_data = fred.get_macro_indicators()
                    market_macro = market_service.get_macro_data()
                    status.write(f"✅ Macro 數據獲取完成: {list(fred_data.keys())} ...")
                    
                    macro_data = {**fred_data, **market_macro}
                    res = macro_agent.run({"macro_data": macro_data})
                    results["Macro"] = res
                    context_texts.append(f"--- Macro Report ---\n{res}")
                    status.write("✅ **Macro Agent**: 分析完成")

                if tickers:
                    status.write(f"📥 正在獲取市場報價: {tickers} ...")
                    # Fetch Data for Tickers
                    prices = market_service.get_current_prices(tickers)
                    status.write(f"✅ 報價獲取完成: {prices}")
                    
                    for ticker in tickers:
                        if "Momentum" in agents_to_call:
                            status.write(f"🔄 **Momentum Agent ({ticker})**: 計算技術指標 (RSI, SMA, MACD)...")
                            mom_agent = AgentFactory.create_momentum_agent()
                            indicators = market_service.get_technical_indicators(ticker)
                            status.write(f"✅ 技術指標計算完成")
                            
                            ctx = {
                                "ticker": ticker,
                                "price_data": {"current_price": prices.get(ticker, 0)},
                                "indicators": indicators
                            }
                            res = mom_agent.run(ctx)
                            results[f"Momentum_{ticker}"] = res
                            context_texts.append(f"--- Momentum Report ({ticker}) ---\n{res}")
                            status.write(f"✅ **Momentum Agent ({ticker})**: 分析完成")

                        if "Fundamental" in agents_to_call:
                            status.write(f"🔄 **Fundamental Agent ({ticker})**: 檢索財報與新聞...")
                            fund_agent = AgentFactory.create_fundamental_agent()
                            fin = market_service.get_financials(ticker)
                            news = market_service.get_news(ticker)
                            status.write(f"✅ 財報與新聞檢索完成 (News count: {len(news)})")
                            
                            ctx = {
                                "ticker": ticker,
                                "financials": fin,
                                "news": news
                            }
                            res = fund_agent.run(ctx)
                            results[f"Fundamental_{ticker}"] = res
                            context_texts.append(f"--- Fundamental Report ({ticker}) ---\n{res}")
                            status.write(f"✅ **Fundamental Agent ({ticker})**: 分析完成")
                
                # 3. Final CIO Synthesis
                if "CIO" in agents_to_call or len(results) > 0:
                    status.write("🧠 **CIO Agent**: 正在綜合各專家意見並生成策略建議...")
                    cio_agent = AgentFactory.create_cio_agent()
                    
                    # Construct ad-hoc context
                    cio_ctx = {
                        "user_id": "interactive_user",
                        "report_focus": "Interactive Chat",
                        "macro_report": results.get("Macro", "N/A"),
                        "momentum_reports": "\n".join([v for k,v in results.items() if "Momentum" in k]),
                        "fundamental_reports": "\n".join([v for k,v in results.items() if "Fundamental" in k]),
                        "leverage_ratio": 1.0, # Default for chat
                        "agent_status": "Interactive Mode"
                    }
                    
                    # Override CIO prompt to answer user question specifically? 
                    # BaseAgent doesn't easily support overriding prompt template at runtime without changing file.
                    # But we can append User Question to the context or the "manual" user prompt.
                    # CIOAgent.run() uses fixed prompt structure. 
                    # But CIO prompt has "Assessment" and "Decision Making".
                    # We might want a "Chat Mode" CIO.
                    # For now, we reuse standard CIO logic, which produces a Report.
                    
                    # Hack: Prepend user question to Macro Report or similar field to force attention?
                    # Properly: CIOAgent run should accept 'user_question'.
                    # Let's just pass it in context and hope standard prompt handles it (it doesn't explicitly).
                    # But CIOAgent uses mocking or Template.
                    
                    # Actually, the best way for Chat is to feed the sub-agent reports + user question to a FINAL LLM call.
                    # CIO's run executes LLM. We can modify CIO input to include "User Question: {prompt}".
                    
                    # Let's modify CIO context to include 'additional_context' if we supported it.
                    # We can put it in 'macro_report' variable as a hack:
                    cio_ctx['macro_report'] = f"User Question: {prompt}\n\n" + cio_ctx['macro_report']
                    
                    final_response = cio_agent.run(cio_ctx)
                    full_response = final_response

                else:
                    full_response = "未能調用到合適的 Agent 或無法識別代碼。"

                status.update(label="完成!", state="complete", expanded=False)
            
            except Exception as e:
                st.error(f"Error: {e}")
                full_response = f"系統發生錯誤: {str(e)}"

        message_placeholder.markdown(full_response)
        st.session_state.messages.append({"role": "assistant", "content": full_response})
