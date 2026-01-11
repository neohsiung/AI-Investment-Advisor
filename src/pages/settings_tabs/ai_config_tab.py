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

        # Smart Model
        smart_default = settings.get("AI_MODEL_SMART", settings.get("AI_MODEL", "gemini-1.5-pro"))
        st.markdown("#### 🧠 Smart Tier (智囊團)")
        st.caption("適用角色: CIO, Macro, Fundamental, Engineer")
        
        if provider == "OpenRouter":
             if 'openrouter_models' not in st.session_state:
                st.session_state['openrouter_models'] = []
             
             col_model, col_btn = st.columns([3, 1])
             with col_btn:
                if st.form_submit_button("更新模型列表 (Fetch Models)"):
                    st.session_state['openrouter_models'] = service.fetch_openrouter_models()
                    st.rerun()

             with col_model:
                if st.session_state['openrouter_models']:
                    if smart_default not in st.session_state['openrouter_models']:
                        st.session_state['openrouter_models'].insert(0, smart_default)
                    model_smart = st.selectbox("Smart Model", st.session_state['openrouter_models'], index=st.session_state['openrouter_models'].index(smart_default))
                else:
                    model_smart = st.text_input("Smart Model", value=smart_default)
        else:
            model_smart = st.text_input("Smart Model", value=smart_default, help="e.g., gemini-1.5-pro, gpt-4o")

        # Fast Model
        fast_default = settings.get("AI_MODEL_FAST", "gemini-1.5-flash")
        st.markdown("#### ⚡ Fast Tier (前鋒部隊)")
        st.caption("適用角色: Momentum, Dispatcher, Daily Check")
        
        if provider == "OpenRouter" and st.session_state.get('openrouter_models'):
             if fast_default not in st.session_state['openrouter_models']:
                st.session_state['openrouter_models'].insert(0, fast_default)
             model_fast = st.selectbox("Fast Model", st.session_state['openrouter_models'], index=st.session_state['openrouter_models'].index(fast_default))
        else:
            model_fast = st.text_input("Fast Model", value=fast_default, help="e.g., gemini-1.5-flash, gpt-4o-mini")

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
