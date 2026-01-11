import streamlit as st
import os
import subprocess
import sys
from src.utils.components import saas_card_start, saas_card_end

def render_report_dry_run_tab(st, user_id):
    saas_card_start(title="Workflow Diagnostic", subtitle="即時測試完整分析流程而不執行發送行為", icon="🧪")

    # 確保 logs 目錄存在
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    log_file = os.path.join(log_dir, "dry_run.log")

    # 初始化 Session State
    if 'dry_run_pid' not in st.session_state:
        st.session_state['dry_run_pid'] = None

    # 檢查執行狀態
    is_running = False
    if st.session_state['dry_run_pid']:
        try:
            # 檢查 PID 是否存在 (僅適用於 Unix)
            os.kill(st.session_state['dry_run_pid'], 0)
            is_running = True
        except OSError:
            is_running = False
            st.session_state['dry_run_pid'] = None

    col_btn, col_status = st.columns([1, 3])

    with col_btn:
        if not is_running:
            if st.button("開始生成測試報告 (Start Dry Run)"):
                # 清空舊 Log
                with open(log_file, "w") as f:
                    f.write(f"Starting Dry Run for user: {user_id}...\n")

                # 非同步啟動, 傳入 user_id
                process = subprocess.Popen(
                    [sys.executable, "src/cli.py", "--mode", "weekly", "--dry-run", "--user_id", user_id],
                    stdout=open(log_file, "a"),
                    stderr=subprocess.STDOUT,
                    preexec_fn=os.setsid # 確保可以被追蹤
                ) # nosec B603
                st.session_state['dry_run_pid'] = process.pid
                st.rerun()
        else:
            st.button("執行中... (Running)", disabled=True)
            if st.button("強制停止 (Stop)"):
                try:
                    os.killpg(os.getpgid(st.session_state['dry_run_pid']), 15) # SIGTERM
                    st.session_state['dry_run_pid'] = None
                    with open(log_file, "a") as f:
                        f.write("\n[Process stopped by user]\n")
                    st.rerun()
                except Exception as e:
                    st.error(f"停止失敗: {e}")

    with col_status:
        if is_running:
            st.warning(f"正在執行中 (PID: {st.session_state['dry_run_pid']}) - 請點擊下方按鈕刷新日誌")
        else:
            st.success("目前無執行任務 (Idle)")

    st.markdown("---")
    st.subheader("執行日誌 (Execution Logs)")

    if st.button("刷新日誌 (Refresh Logs)"):
        pass # 僅觸發 Rerun

    # 讀取並顯示 Log
    if os.path.exists(log_file):
        with open(log_file, "r") as f:
            lines = f.readlines()
            # 顯示最後 50 行
            log_content = "".join(lines[-50:])
            st.code(log_content, language="plaintext")

            # 自動滾動到底部
            if is_running:
                from src.utils.time_utils import get_current_time
                st.caption(f"Last updated: {get_current_time().strftime('%H:%M:%S')}")
    else:
        st.info("尚無日誌檔案。")
    saas_card_end()

    # --- Email Settings & Test ---
    saas_card_start(title="Notification Gateway", subtitle="配置與測試 SMTP 外發服務之連通性", icon="📧")

    sender_email = os.getenv("SMTP_USER", "Not Set")
    recipient_email = os.getenv("EMAIL_RECIPIENT", "Not Set")
    smtp_server = os.getenv("SMTP_HOST", "smtp.gmail.com")

    col1, col2 = st.columns(2)
    with col1:
        st.info(f"**Sender:** {sender_email}")
        st.info(f"**Recipient:** {recipient_email}")
    with col2:
        st.info(f"**SMTP Server:** {smtp_server}")

    if st.button("發送測試郵件 (Send Test Email)"):
        from src.notifier import EmailNotifier
        import logging
        import io

        # Setup log capture
        log_capture_string = io.StringIO()
        ch = logging.StreamHandler(log_capture_string)
        ch.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        ch.setFormatter(formatter)

        logger = logging.getLogger("EmailNotifier")
        logger.addHandler(ch)

        notifier = EmailNotifier()
        with st.spinner("正在發送測試郵件..."):
            success = notifier.send_report(
                "Test Email from AI Investment Advisor",
                "This is a test email to verify your SMTP settings.\n\nIf you received this, your email configuration is correct."
            )

        # Remove handler
        logger.removeHandler(ch)
        log_contents = log_capture_string.getvalue()

        if success:
            st.success("測試郵件發送成功！")
        else:
            st.error("測試郵件發送失敗 (Failed to send test email)")

        with st.expander("查看詳細日誌 (View Detailed Logs)", expanded=True):
            st.code(log_contents)
    saas_card_end()
