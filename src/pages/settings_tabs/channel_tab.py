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

def render_channel_tab(st, settings_service, user_id):
    """
    Renders the Interaction & Channel Management tab.
    互動與通知管理：設定 LINE/Slack/Telegram 及其互動參數。
    分為「個人通知」與「群組協作」兩大類。
    """
    st.header("多渠道矩陣 (Multi-Channel Matrix)")
    st.markdown("---")

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

    # Render Tabs for Personal vs Group
    tab_personal, tab_group = st.tabs(["👤 個人通知 (Personal)", "👥 群組協作 (Group)"])

    def render_channels(container, channels, prompt_text):
        with container:
            st.caption(prompt_text)
            for channel in channels:
                cid = channel['id']
                with st.expander(f"🔹 {channel['name']}", expanded=False):
                    col1, col2 = st.columns([1, 3])
                    
                    with col1:
                        # Toggle Enable/Disable
                        is_enabled = st.toggle(
                            "啟用此渠道", 
                            key=f"channel_{cid}_enabled", 
                            value=settings.get(f"channel_{cid}_enabled", "false") == "true"
                        )
                        
                        # Save enabled state to DB if changed
                        db_enabled = settings.get(f"channel_{cid}_enabled", "false") == "true"
                        if is_enabled != db_enabled:
                            new_val = "true" if is_enabled else "false"
                            settings_service.save_setting(f"channel_{cid}_enabled", new_val)
                            settings[f"channel_{cid}_enabled"] = new_val
                    
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
        from src.services.verification_service import VerificationService
        
        with st.spinner(f"正在透過 {cid} 發送測試訊息..."):
            try:
                import asyncio
                # Instantiate Service with current user_id (email) to load correct settings
                svc = VerificationService(user_id=user_id)
                
                # Check specifics
                target_id = _get_target_id(cid, settings)
                if not target_id:
                     st.error("請先設定 User ID / Chat ID")
                     return

                success, msg = asyncio.run(svc.test_connectivity(target_id, cid))
                
                if success:
                    st.success(f"✅ 測試成功：{msg}")
                else:
                    st.error(f"❌ 發送失敗: {msg}")
                    
            except Exception as e:
                st.error(f"發送失敗 (System): {e}")

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
                # Parse expires_at: SQLite returns strings or datetime objects depending on engine
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

