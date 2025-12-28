import streamlit as st
import pandas as pd
import re
from src.agents.factory import AgentFactory
from src.services.market_data_service import MarketDataService
from src.utils.logger import setup_logger
from src.utils.page_base import BasePage

logger = setup_logger("Page_Chat")


class AdvisorChatPage(BasePage):
    """AI Advisor interactive chat page"""
    
    def __init__(self):
        super().__init__("AI 投資顧問 (Interactive Advisor)", "💬")
    
    def render(self):
        """Render chat interface"""
        st.info("ℹ️ 此對話為即時諮詢模式，內容僅供當下參考，**不會**存入系統的正式週報/月報資料庫，亦不影響例行性績效追蹤。")

        # Initialize chat messages
        if "messages" not in st.session_state:
            st.session_state.messages = []

        # Clear chat input on page load/navigation
        if "chat_input_key" not in st.session_state:
            st.session_state.chat_input_key = 0

        # Display chat history
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

        # Chat input
        prompt = st.chat_input("請問關於投資的問題 (例如: AAPL 現在可以買嗎? / 分析 TSLA 基本面)", key=f"chat_input_{st.session_state.chat_input_key}")

        if prompt:
            # Add user message
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

            # Assistant response
            with st.chat_message("assistant"):
                message_placeholder = st.empty()
                full_response = ""

                with st.status("正在調用 AI Agent...", expanded=True) as status:
                    try:
                        factory = AgentFactory()
                        market_data_service = MarketDataService()

                        # Check for ticker
                        ticker_match = re.search(r'\\b([A-Z]{1,5})\\b', prompt)
                        ticker = ticker_match.group(1) if ticker_match else None

                        if ticker == "AAPL":
                            st.write("偵測到代碼: AAPL")
                            agent = factory.create_stock_analyst_agent()
                            result = agent.run({
                                "ticker": "AAPL",
                                "analyst_type": "fundamental"
                            })
                            full_response = result

                        elif ticker:
                            st.write(f"偵測到代碼: {ticker}")
                            agent = factory.create_stock_analyst_agent()
                            result = agent.run({
                                "ticker": ticker,
                                "analyst_type": "fundamental"
                            })
                            full_response = result

                        else:
                            agent_type = "cio"
                            st.write(f"調用 {agent_type.upper()} Agent...")
                            cio_agent = factory.create_cio_agent()

                            cio_ctx = {
                                'macro_report': "宏觀經濟環境摘要",
                                'portfolio_snapshot': {"total_nlv": 1000},
                                'recent_transactions': []
                            }
                            cio_ctx['macro_report'] = f"User Question: {prompt}\\n\\n" + cio_ctx['macro_report']

                            final_response = cio_agent.run(cio_ctx)
                            full_response = final_response

                        status.update(label="完成!", state="complete", expanded=False)
                        message_placeholder.markdown(full_response)

                    except Exception as e:
                        logger.error(f"Chat error: {e}")
                        full_response = f"抱歉，處理時發生錯誤: {str(e)}"
                        message_placeholder.markdown(full_response)
                        status.update(label=f"完成但有錯誤", state="error")

                # Store assistant response
                st.session_state.messages.append({"role": "assistant", "content": full_response})

                # Increment key to clear chat input for next message
                st.session_state.chat_input_key += 1
                st.rerun()


if __name__ == "__main__":
    AdvisorChatPage().run()
