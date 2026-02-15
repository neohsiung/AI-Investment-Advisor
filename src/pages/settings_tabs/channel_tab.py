import streamlit as st
import os
import time
from src.services.settings_service import SettingsService
from src.services.interaction_service import InteractionService

def _migrate_env_to_settings(settings_service, settings):
    """
    Auto-migrate credentials from .env if they don't exist in DB.
    """
    env_mapping = {
        "LINE_CHANNEL_ACCESS_TOKEN": "channel_line_access_token",
        "LINE_CHANNEL_SECRET": "channel_line_secret",
        "LINE_USER_ID": "channel_line_user_id"
    }
    
    updated = False
    for env_key, setting_key in env_mapping.items():
        if setting_key not in settings or not settings[setting_key]:
            env_val = os.getenv(env_key)
            if env_val:
                settings_service.save_setting(setting_key, env_val)
                settings[setting_key] = env_val # Update local dict
                updated = True
                
    if updated:
        st.toast("✅ 已從環境變數遷移 LINE 設定至資料庫")

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
                    "id": "messenger",
                    "name": "Facebook Messenger",
                    "desc": "Meta 生態系整合。需透過 Meta Developers 設定。",
                    "fields": {
                        "page_token": {"label": "Page Access Token", "type": "password"},
                        "verify_token": {"label": "Verify Token", "type": "password"}
                    },
                    "testable": False
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
                        "channel_id": {"label": "Channel ID", "type": "text", "help": "C012345..."}
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
                    
                    with col2:
                        st.write(channel['desc'])

                    if is_enabled:
                        st.divider()
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
                        
                        # Test Button logic (Simulated for now for non-implemented adapters)
                        st.markdown("---")
                        if st.button(f"傳送測試訊息 ({channel['name']})", key=f"test_{cid}"):
                            _handle_test_message(st, cid, settings)

    def _handle_test_message(st, cid, settings):
        with st.spinner(f"正在透過 {cid} 發送測試訊息..."):
            try:
                # Instantiate Service (It will load updated settings from DB)
                svc = InteractionService() 
                
                # Check specifics for each channel to ensure we have target ID
                target_id = None
                if cid == 'line':
                    target_id = settings.get("channel_line_user_id")
                elif cid == 'telegram':
                    target_id = settings.get("channel_telegram_chat_id")
                elif cid == 'slack':
                    # slack adapter might take channel_id from config or arg
                    target_id = settings.get("channel_slack_channel_id")
                
                # If target_id is needed but missing
                if cid in ['line', 'telegram'] and not target_id:
                     st.error("請先設定 User ID / Chat ID")
                     return

                # Generic Request
                # For MVP, InteractionService.request_approval routes to ALL enabled adapters
                # To test specific channel, we might need a way to target specific adapter 
                # OR we just rely on the fact that if it's enabled, it will send.
                # Since we are in the settings of *this* channel, users imply testing *this* channel.
                # However, InteractionService broadcasts to all *enabled* adapters.
                # If user enables multiple, all will get it.
                # For better UX, we should probably allow InteractionService to target specific adapter.
                # But for now, let's just trigger the broadcast and assume user is focused on this one.
                
                result = svc.request_approval(
                    title=f"Connectivity Test ({cid})",
                    content=f"這是來自 Investment Advisor 的測試訊息。",
                    user_id=target_id, # Might be ignored by some adapters or used as override
                    timeout_seconds=5 
                )
                
                if result:
                    st.success("✅ 測試成功：收到確認或送達！")
                else:
                    st.info("ℹ️ 訊息已發送 (等待確認或無須確認)")
                    
            except Exception as e:
                st.error(f"發送失敗: {e}")

    # Render
    render_channels(tab_personal, channel_groups["個人通知 (Personal Channels)"]["channels"], channel_groups["個人通知 (Personal Channels)"]["desc"])
    render_channels(tab_group, channel_groups["群組協作 (Group Collaboration)"]["channels"], channel_groups["群組協作 (Group Collaboration)"]["desc"])

