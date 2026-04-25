import streamlit as st
import os
import time
from sqlalchemy import text
from src.services.settings_service import SettingsService
from src.services.interaction_service import InteractionService

def _migrate_env_to_settings(settings_service, settings):
    """
    Auto-migrate credentials from .env if they don't exist in DB.
    """
    env_mapping = {
        "LINE_CHANNEL_ACCESS_TOKEN": "channel_line_access_token",
        "LINE_CHANNEL_SECRET": "channel_line_secret",
        "LINE_USER_ID": "channel_line_user_id",
        "SLACK_BOT_TOKEN": "channel_slack_bot_token",
        "SLACK_CHANNEL_ID": "channel_slack_channel_id",
        "TELEGRAM_BOT_TOKEN": "channel_telegram_bot_token",
        "TELEGRAM_CHAT_ID": "channel_telegram_chat_id",
        "MESSENGER_PAGE_TOKEN": "channel_messenger_page_token",
        "MESSENGER_VERIFY_TOKEN": "channel_messenger_verify_token",
        "GOOGLE_CHAT_WEBHOOK_URL": "channel_google_chat_webhook_url",
        "SMTP_HOST": "channel_email_smtp_server",
        "SMTP_PORT": "channel_email_smtp_port",
        "SMTP_USER": "channel_email_smtp_user",
        "SMTP_PASSWORD": "channel_email_smtp_pass",
        "EMAIL_RECIPIENT": "channel_email_to_address"
    }
    
    updated = False
    for env_key, setting_key in env_mapping.items():
        if setting_key not in settings or not settings[setting_key]:
            env_val = os.getenv(env_key)
            if env_val:
                settings_service.save_setting(setting_key, env_val)
                settings[setting_key] = env_val # Update local dict
                if not updated:
                    st.toast("✅ 已從環境變數遷移設定至資料庫")
                updated = True

    # [T1] Auto-enable channels if credentials exist but enabled flag not set
    # Email
    if (settings.get("channel_email_smtp_user") and settings.get("channel_email_smtp_pass") and 
        not settings.get("channel_email_enabled")):
        settings_service.save_setting("channel_email_enabled", True)
        settings["channel_email_enabled"] = True
        updated = True

    # Telegram
    if (settings.get("channel_telegram_bot_token") and settings.get("channel_telegram_chat_id") and 
        not settings.get("channel_telegram_enabled")):
        settings_service.save_setting("channel_telegram_enabled", True)
        settings["channel_telegram_enabled"] = True
        updated = True
    
    # LINE (Optional but good for consistency)
    if (settings.get("channel_line_access_token") and settings.get("channel_line_secret") and 
        not settings.get("channel_line_enabled")):
        settings_service.save_setting("channel_line_enabled", True)
        settings["channel_line_enabled"] = True
        updated = True

def render_channel_tab(st, settings_service, user_id):
    """
    Renders the Interaction & Channel Management tab.
    """
    # 🚨 DIAGNOSTIC LOG
    print(f"DEBUG [ChannelTab]: render_channel_tab for user_id='{user_id}' at {time.strftime('%H:%M:%S')}")
    
    # v4.2.1: Removed redundant header to prevent UI stacking/jump perception
    # The tab already has a label "Interaction & Channels"

    # Load All Settings
    settings = settings_service.get_all_settings()
    
    # Auto-Migrate from ENV
    _migrate_env_to_settings(settings_service, settings)

    # Define Channel Groups
    channel_groups = {
        "個人通知 (Personal Channels)": {
            "priority": 1,
            "desc": "一對一通知與審核，適用於隱私性高的交易確認。",
            "channels": [
                {
                    "id": "line",
                    "name": "LINE Platform",
                    "desc": "台灣最常用的通訊軟體。支援 Flex Message 與 Postback 互動審核。",
                    "fields": {
                        "access_token": {"label": "Channel Access Token (Long-lived)", "type": "password"},
                        "secret": {"label": "Channel Secret", "type": "password"},
                        "user_id": {"label": "User ID (Admin)", "type": "password", "help": "接收通知的管理員 ID (U開頭)"}
                    },
                    "testable": True
                },
                {
                    "id": "telegram",
                    "name": "Telegram",
                    "desc": "高隱私性、速度快。支援 Bot API 與 Inline Keyboard。",
                    "fields": {
                        "bot_token": {"label": "Bot Token", "type": "password", "help": "From @BotFather"},
                        "chat_id": {"label": "Chat ID", "type": "text", "help": "User ID or Channel ID"}
                    },
                    "testable": True
                },
                {
                    "id": "email",
                    "name": "Email Notifications",
                    "desc": "傳統且可靠的通知方式。適用於長篇分析報告或日誌摘要。",
                    "fields": {
                        "smtp_server": {"label": "SMTP Server", "type": "text", "default": "smtp.gmail.com"},
                        "smtp_port": {"label": "SMTP Port", "type": "text", "default": "587"},
                        "smtp_user": {"label": "SMTP Username", "type": "text"},
                        "smtp_pass": {"label": "SMTP Password", "type": "password"},
                        "from_address": {"label": "From Address", "type": "text"},
                        "to_address": {"label": "Recipient Email", "type": "text"}
                    },
                    "testable": True,
                    "verifiable": False
                },
                {
                    "id": "messenger",
                    "name": "Facebook Messenger",
                    "desc": "Meta 生態系整合。需透過 Meta Developers 設定。",
                    "fields": {
                        "page_token": {"label": "Page Access Token", "type": "password"},
                        "verify_token": {"label": "Verify Token", "type": "password"},
                        "app_secret": {"label": "App Secret", "type": "password", "help": "用於 Webhook 簽章驗證 (X-Hub-Signature-256)"}
                    },
                    "testable": True
                }
            ]
        },
        "群組協作 (Group Collaboration)": {
            "priority": 2,
            "desc": "團隊廣播與資訊同步，適用於非敏感資訊或團隊決策。",
            "channels": [
                {
                    "id": "slack",
                    "name": "Slack",
                    "desc": "企業級協作工具。支援 Block Kit 互動介面。",
                    "fields": {
                        "bot_token": {"label": "Bot User OAuth Token", "type": "password", "help": "xoxb-..."},
                        "channel_id": {"label": "Channel ID", "type": "text", "help": "C012345..."},
                        "signing_secret": {"label": "Signing Secret", "type": "password", "help": "用於 Webhook 簽章驗證 (X-Slack-Signature)"}
                    },
                    "testable": True
                },
                {
                    "id": "google_chat",
                    "name": "Google Chat",
                    "desc": "Google Workspace 整合。使用 Webhook 進行簡單通知。",
                    "fields": {
                        "webhook_url": {"label": "Webhook URL", "type": "password"}
                    },
                    "testable": True
                }
            ]
        }
    }

    # Render Tabs for Personal vs Group vs Webhooks
    tab_personal, tab_group, tab_webhooks = st.tabs([
        ":material/person: 個人通知", 
        ":material/groups: 群組協作",
        ":material/webhook: 外部串接"
    ])

    def render_channels(container, channels, prompt_text):
        with container:
            st.caption(prompt_text)
            for channel in channels:
                cid = channel['id']
                with st.expander(f"🔹 {channel['name']}", expanded=False):
                    col1, col2 = st.columns([1, 3])
                    
                    with col1:
                        # [NEW] Robust boolean helper
                        def to_bool(v):
                            if isinstance(v, bool): return v
                            return str(v).lower() == "true"

                        # Toggle Enable/Disable
                        is_enabled = st.toggle(
                            "啟用此渠道", 
                            key=f"channel_{cid}_enabled", 
                            value=to_bool(settings.get(f"channel_{cid}_enabled", False))
                        )
                        
                        # Save enabled state to DB if changed
                        db_enabled = to_bool(settings.get(f"channel_{cid}_enabled", False))
                        if is_enabled != db_enabled:
                            settings_service.save_setting(f"channel_{cid}_enabled", is_enabled)
                            settings[f"channel_{cid}_enabled"] = is_enabled
                    
                    with col2:
                        st.write(channel['desc'])

                    if is_enabled:
                        st.divider()
                        
                        # 1. Interests (通知偏好)
                        st.write("#### 🔔 通知內容偏好 (Notification Interests)")
                        interest_options = {
                            "Sentinel": "sentinel",
                            "分析報告 (Reports)": "report",
                            "交易審核 (Approvals)": "approval"
                        }
                        
                        # Load current interests
                        current_interests_str = settings.get(f"channel_{cid}_interests", "sentinel,report,approval")
                        current_interests = [i.strip().lower() for i in current_interests_str.split(",") if i.strip()]
                        
                        default_interest_values = []
                        for label, val in interest_options.items():
                            if val in current_interests:
                                default_interest_values.append(label)
                        
                        selected_labels = st.multiselect(
                            "選擇接收訊息類型",
                            options=list(interest_options.keys()),
                            default=default_interest_values,
                            key=f"channel_{cid}_interests_ui"
                        )
                        
                        new_interests = ",".join([interest_options[label] for label in selected_labels])
                        if new_interests != current_interests_str:
                            settings_service.save_setting(f"channel_{cid}_interests", new_interests)
                            settings[f"channel_{cid}_interests"] = new_interests
                        
                        st.markdown("---")
                        
                        # 2. Configuration Fields
                        st.write("#### ⚙️ 渠道設定 (Configuration)")
                        scol1, scol2 = st.columns([1, 1])
                        for i, (fname, fmeta) in enumerate(channel['fields'].items()):
                            key = f"channel_{cid}_{fname}"
                            val = settings.get(key, fmeta.get('default', ""))
                            
                            target_col = scol1 if i % 2 == 0 else scol2
                            with target_col:
                                if fmeta.get('type') == 'password':
                                    new_val = st.text_input(fmeta['label'], value=val, type="password", key=f"input_{key}", help=fmeta.get('help', ""))
                                else:
                                    new_val = st.text_input(fmeta['label'], value=val, key=f"input_{key}", help=fmeta.get('help', ""))
                                
                                if new_val != val:
                                    settings_service.save_setting(key, new_val)
                                    settings[key] = new_val # Update local context for immediate use in buttons
                        
                        # Test Button logic
                        st.markdown("---")
                        if channel.get("testable"):
                            st.write("#### 驗證與測試 (Verification)")
                            # If verifiable is False, only show test button
                            if channel.get("verifiable", True):
                                col_test_1, col_test_2 = st.columns(2)
                            else:
                                col_test_1 = st.container()
                                col_test_2 = None
                            
                            with col_test_1:
                                if st.button(f"📶 連線測試 ({channel['name']})", key=f"test_{cid}"):
                                    _handle_test_message(st, cid, settings, user_id)
                            
                            if col_test_2:
                                with col_test_2:
                                    with st.popover(f"🔐 交互驗證 ({channel['name']})"):
                                        st.write("發送驗證碼並等待回覆")
                                        timeout = st.number_input("等待時限 (小時)", min_value=1, value=1, key=f"timeout_{cid}")
                                        if st.button("發送驗證請求", key=f"verify_{cid}"):
                                            _handle_verification(st, cid, settings, timeout, user_id)

                            # Show Pending Status if any
                            _show_verification_status(st, cid, settings, user_id)

    def _handle_test_message(st, cid, settings, user_id):
        import httpx
        import asyncio
        import os
        
        with st.spinner(f"正在透過 {cid} 發送測試訊息..."):
            try:
                target_id = _get_target_id(cid, settings)
                # Fallback to generic key lookup if helper returned None
                if not target_id:
                     target_id = settings.get(f"channel_{cid}_user_id") or settings.get(f"channel_{cid}_to_address") or settings.get(f"channel_{cid}_chat_id") or settings.get(f"channel_{cid}_channel_id")
                
                if not target_id:
                     st.error("請先設定 User ID / Chat ID / Email Address")
                     return

                # Ensure URL is taken from env or fallback
                notification_api_url = os.environ.get("NOTIFICATION_API_URL", "http://localhost:8001/api/v1/notify")
                
                payload = {
                    "user_id": user_id,  # v4.2.2: Use internal user_id for settings lookup
                    "title": f"🔔 {cid.upper()} 渠道測試",
                    "content": f"這是一條從 Investment Advisor Settings 發送的測試訊息。\n時間：{time.strftime('%Y-%m-%d %H:%M:%S')}",
                    "channels": [cid],
                    "category": "system"  # Use 'system' to bypass InterestBasedFilter for tests
                }

                async def send_test():
                    async with httpx.AsyncClient() as client:
                        resp = await client.post(notification_api_url, json=payload, timeout=10.0)
                        return resp

                response = asyncio.run(send_test())
                
                if 200 <= response.status_code < 300:
                    st.success(f"✅ 測試請求已送出至微服務 (排隊中)。")
                else:
                    st.error(f"❌ 服務回應異常: HTTP {response.status_code}")
                    
            except Exception as e:
                st.error(f"發送請求失敗: {e}")

    def _handle_verification(st, cid, settings, timeout, user_id):
        from src.services.verification_service import VerificationService
        with st.spinner("啟動驗證流程..."):
            import asyncio
            svc = VerificationService(user_id=user_id)
            target_id = _get_target_id(cid, settings)
            if not target_id:
                 st.error("請先設定 User ID / Chat ID")
                 return
                 
            # Pass internal user_id (email) for DB record, AND target_id (channel-specific) for early mapping
            success, msg, vid = asyncio.run(svc.initiate_verification(user_id, cid, timeout_hours=timeout, channel_user_id=target_id))
            if success:
                st.success(f"已發送驗證請求！{msg}")
            else:
                st.error(f"啟動失敗: {msg}")

    def _show_verification_status(st, cid, settings, user_id):
        from src.repositories.verification_repository import AlchemyVerificationRepository
        from datetime import datetime, timezone
        repo = AlchemyVerificationRepository()
        
        # Get the most recent record regardless of status to show results
        query = text("""
            SELECT id, user_id, channel, channel_user_id, code, status, error_message, expires_at, created_at 
            FROM channel_verifications 
            WHERE (user_id = :user_id OR channel_user_id = :user_id) AND channel = :channel
            ORDER BY created_at DESC LIMIT 1
        """)
        try:
            from src.data.database import get_db_connection
            with get_db_connection(repo.engine) as conn:
                row = conn.execute(query, {"user_id": user_id, "channel": cid}).fetchone()
                pending = repo._to_dict(row) if row else None
        except:
            pending = None
        
        if pending:
            status = pending['status']
            if status == 'verified':
                st.success(f"✅ {cid.upper()} 驗證成功！管道已啟動。")
                return
            
            if status == 'failed':
                st.error(f"❌ 驗證失敗：{pending['error_message']}")
                return

            if status == 'pending':
                # Parse expires_at: PostgreSQL returns datetime/TIMESTAMPTZ objects.
                ext = pending['expires_at']
                if isinstance(ext, str):
                    ext = ext.replace(' ', 'T')
                    if '.' in ext:
                        ext = ext.split('.')[0]
                    try:
                        ext_dt = datetime.fromisoformat(ext)
                    except:
                        st.warning(f"解析時間失敗: {ext}")
                        return
                else:
                    ext_dt = ext
                
                # Compare in UTC
                now_utc = datetime.utcnow()
                # Ensure ext_dt is naive if now_utc is naive (which utcnow is)
                if ext_dt.tzinfo is not None:
                    ext_dt = ext_dt.replace(tzinfo=None)
                
                diff = ext_dt - now_utc
                minutes = int(diff.total_seconds() / 60)
                
                if minutes > 0:
                    st.info(f"⏳ 等待驗證中... (預計於 {minutes} 分鐘後過期)")
                    st.caption(f"請在您的 {cid.upper()} 頻道中回覆 '{pending['code']}'")
                else:
                    st.warning("⚠️ 驗證已過期，請重新嘗試。")

    def _get_target_id(cid, settings):
        if cid == 'line':
            return settings.get("channel_line_user_id")
        elif cid == 'telegram':
            return settings.get("channel_telegram_chat_id")
        elif cid == 'slack':
            return settings.get("channel_slack_channel_id")
        elif cid == 'email':
            return settings.get("channel_email_to_address")
        return None

    # Render
    render_channels(tab_personal, channel_groups["個人通知 (Personal Channels)"]["channels"], channel_groups["個人通知 (Personal Channels)"]["desc"])
    render_channels(tab_group, channel_groups["群組協作 (Group Collaboration)"]["channels"], channel_groups["群組協作 (Group Collaboration)"]["desc"])
    _render_webhooks_tab(tab_webhooks, settings_service, user_id, settings)

def _render_webhooks_tab(container, settings_service, user_id, settings):
    """
    Renders the Incoming Webhook management interface.
    """
    with container:
        st.write("### 🪝 外部訊號串接 (Incoming Webhooks)")
        st.caption("透過 API Key 從外部系統（如 TradingView, n8n）發送訊號至 Investment Advisor。")
        
        # 1. Base URL
        # URL logic: Base URL of mcp_server. 
        # In multi-tenant SaaS, this would typically be a specific per-user endpoint, 
        # but in our architecture, we route via X-API-Key to a shared generic endpoint.
        webhook_url = os.environ.get("WEBHOOK_BASE_URL", "http://localhost:8000/api/v1/webhook/generic")
        st.info(f"**Webhook 接收網址 (Generic Endpoint)**: `{webhook_url}`")
        
        st.divider()
        
        # 2. API Key Management
        api_key = settings.get("webhook_api_key", "")
        
        col1, col2 = st.columns([3, 1])
        with col1:
            if api_key:
                st.write("**您的 API Key**")
                # Masked display logic
                display_key = api_key
                if "show_webhook_key" not in st.session_state:
                    st.session_state.show_webhook_key = False
                
                if not st.session_state.show_webhook_key:
                    display_key = "•" * 24
                
                st.code(display_key, language="text")
                st.checkbox("顯示原始金鑰 (Show raw key)", key="show_webhook_key")
            else:
                st.warning("⚠️ 尚未生成 API Key。請點擊「重新產生」以獲取新金鑰。")
        
        with col2:
            st.write("**動作 (Actions)**")
            # Rotate Button
            if st.button("🔄 重新產生", help="產生新的金鑰，舊的金鑰將立即失效。", use_container_width=True):
                with st.popover("⚠️ 確認重新產生？"):
                    st.warning("這將立即中斷所有使用舊金鑰的外部整合。")
                    if st.button("確認產生 (Rotate)", type="primary", key="confirm_rotate", use_container_width=True):
                        import secrets
                        new_key = f"sk_{secrets.token_hex(20)}"
                        success, _ = settings_service.save_setting("webhook_api_key", new_key)
                        if success:
                            st.toast("✅ 已產生新金鑰！")
                            st.rerun()

            # Revoke Button
            if api_key:
                if st.button("🗑️ 撤銷金鑰", help="刪除目前的金鑰。", use_container_width=True):
                    with st.popover("🚨 確認撤銷？"):
                        st.error("撤銷後，所有 Webhook 訊號將被拒絕。")
                        if st.button("確認撤銷 (Revoke)", type="primary", key="confirm_revoke", use_container_width=True):
                            success, _ = settings_service.delete_setting("webhook_api_key")
                            if success:
                                st.toast("✅ 金鑰已撤銷。")
                                st.rerun()

        # 3. Usage Guide
        if api_key:
            st.divider()
            st.write("### 💡 使用指南 (Usage Guide)")
            st.markdown(f"""
            請在您的 `POST` 請求 Header 中加入：
            ```http
            X-API-Key: {api_key}
            Content-Type: application/json
            ```
            
            **範例 (cURL):**
            ```bash
            curl -X POST {webhook_url} \\
                 -H "X-API-Key: {api_key}" \\
                 -H "Content-Type: application/json" \\
                 -d '{{"type": "ticker_alert", "symbol": "BTC/USDT", "action": "buy"}}'
            ```
            """)
        else:
            st.info("若要啟動外部串接功能，請先重新產生 API Key。")

