import os
import requests
import json
from src.infrastructure.channels.telegram_adapter import TelegramAdapter
from src.infrastructure.channels.line_adapter import LineBotAdapter

def test_telegram():
    token = "8387063740:AAFBzC0k2VKBZG5h1JuV4WozrMp_CA9fHqA"
    chat_id = "982605706"
    print(f"Testing Telegram to {chat_id}...")
    adapter = TelegramAdapter(bot_token=token, chat_id=chat_id)
    success = adapter.send_alert(chat_id, "Test Connectivity", "This is a direct test message.")
    print(f"Telegram Success: {success}")

def test_line():
    token = "pOPOuWE9fFNNRheHYh3TscgdcAqfo/F6D0fhgbz2qjCWsYXLwOIzyDnFcxS2pr79SEb4wGudWN52HJchBDQeq2r/j02u7pDy4cL6vWpIrIVHvwl7bcYn4hqPSfhuAHX3/7Ao/deDcScYRysa/QqxKQdB04t89/1O/w1cDnyilFU="
    secret = "f51bdb15e373e96775e191007369afa4"
    user_id = "U89230a0a471836b5533901492ed503bc"
    print(f"Testing LINE to {user_id}...")
    adapter = LineBotAdapter(channel_access_token=token, channel_secret=secret, line_user_id=user_id)
    success = adapter.send_alert(user_id, "Test Connectivity", "This is a direct test message.")
    print(f"LINE Success: {success}")

if __name__ == "__main__":
    test_telegram()
    test_line()
