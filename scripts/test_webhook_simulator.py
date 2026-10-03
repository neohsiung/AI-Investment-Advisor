#!/usr/bin/env python3
"""
Webhook Interactive Simulator (Webhook 交互仿真測試器)
=====================================================
模擬 Telegram Bot 回調與 Slack Block Kit 互動請求，
驗證 Webhook Router -> ActionableAlertHubService 的全鏈路行控執行與響應。

支援模式：
1. In-process TestClient (預設，不需外網或啟動容器)
2. Live HTTP mode (--live，向 127.0.0.1:8000 實際發送 HTTP 請求)
"""

import argparse
import asyncio
import json
import os
import sys
from urllib.parse import urlencode

# Ensure root directory is on PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("PRIMARY_USER_ID", "default_user")
os.environ.setdefault("TEST_ENV", "true")

from starlette.testclient import TestClient


def create_mock_telegram_callback(callback_data: str, user_id: int = 123456789) -> dict:
    return {
        "update_id": 999001,
        "callback_query": {
            "id": "cb_query_test_123",
            "from": {
                "id": user_id,
                "is_bot": False,
                "first_name": "TestTrader",
                "username": "test_trader"
            },
            "message": {
                "message_id": 88801,
                "chat": {"id": user_id, "type": "private"},
                "text": "🚨 警報測試訊息"
            },
            "data": callback_data
        }
    }


def create_mock_telegram_message(text: str, user_id: int = 123456789) -> dict:
    return {
        "update_id": 999002,
        "message": {
            "message_id": 88802,
            "from": {
                "id": user_id,
                "is_bot": False,
                "first_name": "TestTrader",
                "username": "test_trader"
            },
            "chat": {"id": user_id, "type": "private"},
            "text": text,
            "date": 1700000000
        }
    }


def create_mock_slack_block_action(action_id: str, value: str) -> dict:
    payload = {
        "type": "block_actions",
        "user": {"id": "U123456", "username": "slack_trader"},
        "actions": [
            {
                "action_id": action_id,
                "block_id": "b_1",
                "value": value
            }
        ]
    }
    return payload


def run_simulation(live_url: str = None):
    print("=" * 60)
    print("🚀 Running Webhook & Actionable Alert Simulator")
    print("=" * 60)

    if live_url:
        import httpx
        client = httpx.Client(base_url=live_url, timeout=10.0)
        print(f"[*] Target mode: LIVE HTTP at {live_url}")
    else:
        from services.mcp_server.src.app.main import app
        client = TestClient(app)
        print("[*] Target mode: In-process TestClient (FastAPI app)")

    # 1. Test Telegram Callback Query - Pause Trading
    print("\n[Case 1] Simulating Telegram Callback: action=pause_trading")
    tg_payload = create_mock_telegram_callback("action=pause_trading")
    res = client.post("/webhook/telegram", json=tg_payload)
    print(f"Status Code: {res.status_code}")
    print(f"Response: {res.json()}")
    assert res.status_code == 200
    assert res.json().get("ok") is True
    print("✓ Case 1 Passed!")

    # 2. Test Telegram Callback Query - Resume Trading
    print("\n[Case 2] Simulating Telegram Callback: action=resume_trading")
    tg_payload = create_mock_telegram_callback("action=resume_trading")
    res = client.post("/webhook/telegram", json=tg_payload)
    print(f"Status Code: {res.status_code}")
    print(f"Response: {res.json()}")
    assert res.status_code == 200
    assert res.json().get("ok") is True
    print("✓ Case 2 Passed!")

    # 3. Test Telegram Slash Command - /support NVDA
    print("\n[Case 3] Simulating Telegram Command: /support NVDA")
    tg_cmd = create_mock_telegram_message("/support NVDA")
    res = client.post("/webhook/telegram", json=tg_cmd)
    print(f"Status Code: {res.status_code}")
    print(f"Response: {res.json()}")
    assert res.status_code == 200
    assert res.json().get("ok") is True
    print("✓ Case 3 Passed!")

    # 4. Test Telegram Slash Command - /shadow
    print("\n[Case 4] Simulating Telegram Command: /shadow")
    tg_cmd = create_mock_telegram_message("/shadow")
    res = client.post("/webhook/telegram", json=tg_cmd)
    print(f"Status Code: {res.status_code}")
    print(f"Response: {res.json()}")
    assert res.status_code == 200
    assert res.json().get("ok") is True
    print("✓ Case 4 Passed!")

    # 5. Test Slack Interactivity Block Action - close_pos
    print("\n[Case 5] Simulating Slack Interactivity: action=close_pos&ticker=MOCK")
    slack_data = create_mock_slack_block_action("btn_close", "action=close_pos&ticker=MOCK")
    form_encoded = urlencode({"payload": json.dumps(slack_data)})
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    res = client.post("/webhook/slack", content=form_encoded, headers=headers)
    print(f"Status Code: {res.status_code}")
    print(f"Response: {res.json()}")
    assert res.status_code == 200
    assert res.json().get("ok") is True
    print("✓ Case 5 Passed!")

    print("\n" + "=" * 60)
    print("✨ ALL SIMULATION CASES PASSED SUCCESSFULLY!")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Webhook Interactive Simulator")
    parser.add_argument("--live", type=str, default="", help="Live API URL (e.g. http://127.0.0.1:8000)")
    args = parser.parse_args()

    run_simulation(live_url=args.live if args.live else None)
