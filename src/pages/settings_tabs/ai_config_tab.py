import streamlit as st
from src.services.settings_service import SettingsService
from src.utils.components import saas_card_start, saas_card_end

def render_api_settings(st, service: SettingsService, settings: dict):
    saas_card_start(title="AI Model Parameters", subtitle="配置核心 AI 調度提供者與模型分級設定", icon="🧠")

    with st.form("ai_settings_form"):
        provider_options = {
            "Google Gemini": "Google Gemini (Google AI)",
            "OpenRouter": "OpenRouter (Router)",
            "OpenAI": "OpenAI (OpenAI)"
        }
        current_provider = settings.get("AI_PROVIDER", "Google Gemini")
        # Ensure current provider is in options
        if current_provider not in provider_options:
            provider_index = 0
        else:
            provider_index = list(provider_options.keys()).index(current_provider)

        provider_key = st.selectbox(
            "AI 提供者 (Provider)",
            options=list(provider_options.keys()),
            format_func=lambda x: provider_options[x],
            index=provider_index
        )
        provider = provider_key

        st.markdown("### 模型分級設定 (Model Tiering)")
        st.info("請為不同任務需求設定合適的模型。Smart Tier 用於深度分析，Fast Tier 用於快速篩選。")

        # OpenRouter Model Fetcher (Shared)
        if provider == "OpenRouter":
            if 'openrouter_models' not in st.session_state:
                st.session_state['openrouter_models'] = []
            
            col_fetch, col_status = st.columns([1, 3])
            with col_fetch:
                if st.form_submit_button("🔄 更新模型列表 (Fetch Models)"):
                    st.session_state['openrouter_models'] = service.fetch_openrouter_models()
                    st.rerun()
            with col_status:
                if st.session_state['openrouter_models']:
                    st.caption(f"已讀取 {len(st.session_state['openrouter_models'])} 個模型 (Shared List)")

        # 3-Column Layout for Tiers
        col_adv, col_smart, col_fast = st.columns(3)

        # --- Advanced Tier ---
        with col_adv:
            advanced_default = settings.get("AI_MODEL_ADVANCED", settings.get("AI_MODEL_SMART", "claude-3-5-sonnet-20240620"))
            st.markdown("#### 🚀 Advanced (戰略)")
            st.caption("Task Planner, Gap Filling")
            
            if provider == "OpenRouter" and st.session_state.get('openrouter_models'):
                if advanced_default not in st.session_state['openrouter_models']:
                    st.session_state['openrouter_models'].insert(0, advanced_default)
                model_advanced = st.selectbox("核心模型", st.session_state['openrouter_models'], index=st.session_state['openrouter_models'].index(advanced_default), key="sel_adv")
            else:
                model_advanced = st.text_input("核心模型", value=advanced_default, key="inp_adv")

        # --- Smart Tier ---
        with col_smart:
            smart_default = settings.get("AI_MODEL_SMART", settings.get("AI_MODEL", "gemini-1.5-pro"))
            st.markdown("#### 🧠 Smart (智囊)")
            st.caption("CIO, Macro, Fundamental")

            if provider == "OpenRouter" and st.session_state.get('openrouter_models'):
                if smart_default not in st.session_state['openrouter_models']:
                    st.session_state['openrouter_models'].insert(0, smart_default)
                model_smart = st.selectbox("分析模型", st.session_state['openrouter_models'], index=st.session_state['openrouter_models'].index(smart_default), key="sel_smart")
            else:
                model_smart = st.text_input("分析模型", value=smart_default, key="inp_smart")

        # --- Fast Tier ---
        with col_fast:
            fast_default = settings.get("AI_MODEL_FAST", "gemini-1.5-flash")
            st.markdown("#### ⚡ Fast (前鋒)")
            st.caption("Momentum, Dispatcher")

            if provider == "OpenRouter" and st.session_state.get('openrouter_models'):
                if fast_default not in st.session_state['openrouter_models']:
                    st.session_state['openrouter_models'].insert(0, fast_default)
                model_fast = st.selectbox("速度模型", st.session_state['openrouter_models'], index=st.session_state['openrouter_models'].index(fast_default), key="sel_fast")
            else:
                model_fast = st.text_input("速度模型", value=fast_default, key="inp_fast")

        api_key = st.text_input(
            "API Key",
            value=settings.get("API_KEY", ""),
            type="password",
            help="請輸入對應 Provider 的 API Key"
        )

        base_url = st.text_input(
            "Base URL (Optional)",
            value=settings.get("BASE_URL", ""),
            help="若使用 OpenRouter 或自定義端點請填寫，否則留空"
        )

        submitted = st.form_submit_button("儲存設定 (Save Settings)")

        if submitted:
            updates = {
                "AI_PROVIDER": provider,
                "AI_MODEL": model_smart, 
                "AI_MODEL_ADVANCED": model_advanced,
                "AI_MODEL_SMART": model_smart,
                "AI_MODEL_FAST": model_fast,
                "API_KEY": api_key,
                "BASE_URL": base_url
            }
            success, msg = service.save_settings_bulk(updates)
            if success:
                st.success(msg)
            else:
                st.error(msg)
    saas_card_end()
