import streamlit as st
import json
from src.utils.components import saas_card_start, saas_card_end

def render_agent_playground_tab(st):
    saas_card_start(title="Agent Playground", subtitle="獨立測試各個 AI Agent 的邏輯處理能力", icon="🎮")

    agent_options = {
        "Momentum": "Momentum (動能專家)",
        "Fundamental": "Fundamental (基本面專家)",
        "Macro": "Macro (總經專家)",
        "CIO": "CIO (投資長)",
        "Engineer": "Engineer (系統工程師)"
    }
    agent_key = st.selectbox("選擇 Agent (Select Agent)", options=list(agent_options.keys()), format_func=lambda x: agent_options[x], key="playground_agent_select")
    agent_type = agent_key

    default_context = ""
    if agent_type == "Momentum":
        default_context = """{
    "ticker": "AAPL",
    "price": 220.5,
    "indicators": {
        "rsi": 65.5,
        "macd": "bullish",
        "macd_val": 1.25
    }
}"""
    elif agent_type == "Fundamental":
        default_context = """{
    "ticker": "AAPL",
    "financials": {
        "market_cap": 3400000000000,
        "trailing_pe": 35.2,
        "forward_pe": 28.5,
        "revenue_growth": 0.05,
        "profit_margins": 0.26
    },
    "news": [
        "Apple Intelligence features rolling out in iOS 18.1 (https://...)",
        "Analyst raises price target on strong services growth (https://...)"
    ]
}"""
    elif agent_type == "Macro":
        default_context = """{
    "macro_data": {
        "^VIX": 15.2,
        "^TNX": 4.35,
        "SPY": 580.0
    }
}"""
    elif agent_type == "CIO":
        default_context = """{
    "macro_report": "## Macro Outlook\\nRisk-On environment supported by stable yields (4.35%) and low VIX (15.2).",
    "momentum_reports": [
        "AAPL: { 'signal': 'BUY', 'reasoning': 'RSI 65.5 indicates strong momentum but not overbought.' }",
        "NVDA: { 'signal': 'HOLD', 'reasoning': 'Consolidating after recent highs.' }"
    ],
    "fundamental_reports": [
        "AAPL: Strong services revenue growth (5%) supports premium valuation (PE 35.2).",
        "NVDA: AI demand remains robust, forward PE attractive."
    ],
    "leverage_ratio": 1.1
}"""
    elif agent_type == "Engineer":
        default_context = """{
    "cio_report": "## System Optimization Feedback\\nCIO suggests that Momentum Agent should include explicit Volume Analysis for better trend confirmation.",
    "target_agent_name": "Momentum"
}"""

    context_input = st.text_area("輸入測試 Context (JSON)", value=default_context, height=200, key="playground_context_input")

    if st.button(f"執行 {agent_type} Agent", key="playground_run_btn"):
        try:
            context = json.loads(context_input)

            # 動態載入 Agent
            if agent_type == "Momentum":
                from src.agents.momentum import MomentumAgent
                agent = MomentumAgent()
            elif agent_type == "Fundamental":
                from src.agents.fundamental import FundamentalAgent
                agent = FundamentalAgent()
            elif agent_type == "Macro":
                from src.agents.macro import MacroAgent
                agent = MacroAgent()
            elif agent_type == "CIO":
                from src.agents.cio import CIOAgent
                agent = CIOAgent()
            elif agent_type == "Engineer":
                from src.agents.engineer import SystemEngineerAgent
                agent = SystemEngineerAgent()

            with st.spinner(f"正在執行 {agent_type} 代理人..."):
                response = agent.run(context)

            st.success("執行成功！")
            st.markdown("### Agent 輸出 (Output)")
            st.markdown(response)

            with st.expander("查看原始回應 (Raw Response)"):
                st.code(response)

        except json.JSONDecodeError:
            st.error("JSON 格式錯誤，請檢查 Context 輸入。")
        except Exception as e:
            st.error(f"執行失敗: {e}")
    saas_card_end()
