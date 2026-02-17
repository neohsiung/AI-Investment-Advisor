import hmac
import hashlib
import time
import json
import os
import sys

# Add src to path
sys.path.append(os.getcwd())

from src.infrastructure.channels.slack_adapter import SlackAdapter
from src.infrastructure.channels.messenger_adapter import MessengerAdapter

def test_slack_verification():
    secret = "test_signing_secret"
    adapter = SlackAdapter(bot_token="xoxb-test", channel_id="C123", signing_secret=secret)
    
    timestamp = str(int(time.time()))
    payload = {"type": "block_actions", "actions": []}
    body = json.dumps(payload, separators=(',', ':'))
    
    sig_basestring = f"v0:{timestamp}:{body}"
    computed_signature = 'v0=' + hmac.new(
        secret.encode(),
        sig_basestring.encode(),
        hashlib.sha256
    ).hexdigest()
    
    headers = {
        'X-Slack-Signature': computed_signature,
        'X-Slack-Request-Timestamp': timestamp
    }
    
    # 1. Test Valid Signature
    is_valid = adapter.verify_signature(payload, headers)
    print(f"Slack Valid Signature Test: {is_valid}")
    assert is_valid == True
    
    # 2. Test Invalid Signature
    headers['X-Slack-Signature'] = 'v0=wrong'
    is_valid = adapter.verify_signature(payload, headers)
    print(f"Slack Invalid Signature Test: {is_valid}")
    assert is_valid == False

def test_messenger_verification():
    secret = "test_app_secret"
    adapter = MessengerAdapter(page_token="page_token", verify_token="verify", app_secret=secret)
    
    payload = {"object": "page", "entry": []}
    body = json.dumps(payload, separators=(',', ':'))
    
    computed_sig = hmac.new(
        secret.encode(),
        body.encode(),
        hashlib.sha256
    ).hexdigest()
    
    headers = {
        'X-Hub-Signature-256': f"sha256={computed_sig}"
    }
    
    # 1. Test Valid Signature
    is_valid = adapter.verify_signature(payload, headers)
    print(f"Messenger Valid Signature Test: {is_valid}")
    assert is_valid == True
    
    # 2. Test Invalid Signature
    headers['X-Hub-Signature-256'] = 'sha256=wrong'
    is_valid = adapter.verify_signature(payload, headers)
    print(f"Messenger Invalid Signature Test: {is_valid}")
    assert is_valid == False

if __name__ == "__main__":
    try:
        test_slack_verification()
        test_messenger_verification()
        print("\n✅ All signature verification tests passed!")
    except AssertionError as e:
        print(f"\n❌ Test failed!")
        sys.exit(1)
