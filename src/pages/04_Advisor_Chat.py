import streamlit as st
import pandas as pd
import re
from src.agents.factory import AgentFactory
from src.services.market_data_service import MarketDataService
from src.utils.logger import setup_logger
from src.utils.page_base import BasePage
from src.utils.components import saas_alert

logger = setup_logger("Page_Chat")


class AdvisorChatPage(BasePage):
    """AI Advisor interactive chat page"""
    
    def __init__(self):
        super().__init__("AI 投資顧問 (Interactive Advisor)", "💬")
    
    def render(self):
        """Render chat interface"""
        saas_alert("此對話為即時諮詢模式，內容僅供當下參考，**不會**存入系統的正式資料庫，亦不影響例行性績效追蹤。", style="info", title="Real-time Advisory Mode")

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

                        # Get User ID for authentic DB config loading
                        user_id = self.user.get('id', 'system') if hasattr(self, 'user') else 'system'

                        # Always use CIO Agent for Interactive Advisory
                        cio_agent = factory.create_cio_agent(user_id=user_id)
                        
                        system_prompt = (
                            "You are a professional AI Investment Advisor. "
                            "Your goal is to answer the user's financial questions concisely, directly, and interactively. "
                            "Do NOT generate a full multi-section weekly/daily report unless explicitly asked. "
                            "Provide actionable, insightful, and data-driven responses. "
                            "Use traditional Chinese (繁體中文)."
                        )
                        
                        # Add ticker context if detected
                        if ticker:
                            system_prompt += f"\\n\\nThe user is asking about the ticker: {ticker}. Please focus your advice on this asset if relevant."
                            st.write(f"已識別標的: {ticker}")

                        messages = [{"role": "system", "content": system_prompt}]
                        
                        # Append short dialogue history (last 5 messages) for conversational memory
                        for msg in st.session_state.messages[-5:]:
                            if msg["role"] != "system":
                                messages.append(msg)
                                
                        messages.append({"role": "user", "content": prompt})

                        # Call LLM directly for interactive response
                        full_response = cio_agent.call_llm(messages=messages, temperature=0.7)
                        
                        status.update(label="分析完成!", state="complete", expanded=False)
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
