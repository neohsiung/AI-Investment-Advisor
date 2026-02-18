
import os
import requests
import uuid
import logging
import json

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("EtoroDebug")

def log_transaction(response):
    req = response.request
    
    print("\n" + "="*60)
    print(f"REQUEST: {req.method} {req.url}")
    print("HEADERS:")
    for k, v in req.headers.items():
        # Cleanly display headers
        print(f"  {k}: {v}")
    
    if req.body:
        print(f"BODY:\n{req.body}")
    else:
        print("BODY: <None>")

    print("-" * 60)
    print(f"RESPONSE: {response.status_code} {response.reason}")
    print("HEADERS:")
    for k, v in response.headers.items():
        print(f"  {k}: {v}")
    
    print("BODY:")
    try:
        print(json.dumps(response.json(), indent=2))
    except:
        print(response.text)
    print("="*60 + "\n")

def main():
    api_key = os.getenv("ETORO_API_KEY")
    user_key = os.getenv("ETORO_USER_KEY")
    base_url = os.getenv("ETORO_API_BASE_URL", "https://public-api.etoro.com")
    
    print(f"Checking Environment Variables:")
    print(f"  ETORO_API_KEY: {'[SET]' if api_key else '[MISSING]'} ({api_key[:10]}... if set)")
    print(f"  ETORO_USER_KEY: {'[SET]' if user_key else '[MISSING]'} ({user_key[:10]}... if set)")
    print(f"  BASE_URL: {base_url}")
    
    if not api_key or not user_key:
        print("❌ Missing updated credentials. Please check .env file.")
        return

    headers = {
        "Content-Type": "application/json",
        "x-request-id": str(uuid.uuid4()),
        "x-api-key": api_key,
        "x-user-key": user_key
    }

    # Test 1: Public Search (Low permission? Usually works if Key is valid)
    print("\n--------------------------------------------------")
    print("TEST 1: Symbol Search (Public Data)")
    print("--------------------------------------------------")
    try:
        url = f"{base_url}/api/v1/market-data/search"
        params = {"internalSymbolFull": "AAPL"}  # Apple
        
        # Prepare request but don't send yet to log pre-send state if needed, 
        # but requests.get does it all. We log after.
        response = requests.get(url, headers=headers, params=params, timeout=15)
        log_transaction(response)
        
    except Exception as e:
        print(f"❌ Test 1 Failed with Exception: {e}")

    # Test 2: Watchlists (User Data - Read Only)
    print("\n--------------------------------------------------")
    print("TEST 2: Get Watchlists (User Data)")
    print("--------------------------------------------------")
    try:
        url = f"{base_url}/api/v1/watchlists"
        response = requests.get(url, headers=headers, timeout=15)
        log_transaction(response)
    except Exception as e:
        print(f"❌ Test 2 Failed with Exception: {e}")

    # Test 3: Portfolio (Private Data - Trading Scope?)
    print("\n--------------------------------------------------")
    print("TEST 3: Get Portfolio (Sensitive Data)")
    print("--------------------------------------------------")
    try:
        url = f"{base_url}/api/v1/trading/info/portfolio"
        response = requests.get(url, headers=headers, timeout=15)
        log_transaction(response)
    except Exception as e:
        print(f"❌ Test 3 Failed with Exception: {e}")

if __name__ == "__main__":
    main()
