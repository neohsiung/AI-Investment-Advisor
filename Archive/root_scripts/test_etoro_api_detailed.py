#!/usr/bin/env python3
"""
eToro API 詳細測試工具
Detailed eToro API testing tool with full request/response logging
"""

import os
os.environ['DB_TYPE'] = 'postgres'
os.environ['DB_HOST'] = 'localhost'
os.environ['DB_USER'] = 'postgres'
os.environ['DB_PASS'] = 'postgres'
os.environ['DB_NAME'] = 'portfolio'

import requests
import json
import uuid
from src.data.database import get_db_connection
from sqlalchemy import text

def get_etoro_credentials():
    """從資料庫獲取 eToro API 憑證"""
    conn = get_db_connection()
    user_id = '90693c07-6177-42df-97d9-915f3ce7c573'
    
    result = conn.execute(text(
        "SELECT key, value FROM settings WHERE user_id = :uid AND key IN ('etoro_api_key', 'etoro_user_key')"
    ), {'uid': user_id}).fetchall()
    
    credentials = {}
    for row in result:
        key, value = row[0], row[1]
        # Parse JSON value
        try:
            parsed_value = json.loads(value) if isinstance(value, str) else value
        except:
            parsed_value = value
        credentials[key] = parsed_value
    
    conn.close()
    return credentials

def test_api_endpoint(url, headers, method='GET', payload=None):
    """
    測試 API 端點並顯示完整的請求和響應
    """
    print("\n" + "=" * 80)
    print(f"測試端點: {url}")
    print("=" * 80)
    
    # 顯示 Request Headers
    print("\n[REQUEST HEADERS]")
    for key, value in headers.items():
        if key in ['x-api-key', 'x-user-key']:
            print(f"  {key}: {value[:30]}...")
        else:
            print(f"  {key}: {value}")
    
    # 顯示 Request Payload
    if payload:
        print("\n[REQUEST PAYLOAD]")
        print(f"  {json.dumps(payload, indent=2)}")
    
    # 發送請求
    try:
        if method == 'GET':
            response = requests.get(url, headers=headers, timeout=10)
        elif method == 'POST':
            response = requests.post(url, headers=headers, json=payload, timeout=10)
        
        # 顯示 Response
        print(f"\n[RESPONSE STATUS]")
        print(f"  Status Code: {response.status_code}")
        print(f"  Reason: {response.reason}")
        
        print(f"\n[RESPONSE HEADERS]")
        for key, value in response.headers.items():
            print(f"  {key}: {value}")
        
        print(f"\n[RESPONSE BODY]")
        try:
            response_json = response.json()
            print(f"  {json.dumps(response_json, indent=2, ensure_ascii=False)}")
        except:
            print(f"  {response.text[:500]}")
        
        return response
        
    except Exception as e:
        print(f"\n[ERROR]")
        print(f"  {str(e)}")
        return None

def main():
    print("=" * 80)
    print("eToro API 詳細測試工具")
    print("=" * 80)
    
    # 獲取憑證
    print("\n[1] 從資料庫載入憑證...")
    credentials = get_etoro_credentials()
    
    if not credentials.get('etoro_api_key') or not credentials.get('etoro_user_key'):
        print("❌ 無法載入 eToro API 憑證")
        return
    
    api_key = credentials['etoro_api_key']
    user_key = credentials['etoro_user_key']
    
    print(f"  API Key: {api_key[:30]}...")
    print(f"  User Key: {user_key[:30]}...")
    
    # 準備 Headers
    headers = {
        'x-request-id': str(uuid.uuid4()),
        'x-api-key': api_key,
        'x-user-key': user_key,
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    }
    
    base_url = "https://public-api.etoro.com"
    
    # 測試不同的端點
    endpoints = [
        "/api/v1/watchlists",
        "/api/v1/portfolio",
        "/api/v1/positions",
        "/api/v1/trades",
        "/api/v1/account",
        "/api/v1/trading/info/portfolio",
        "/api/v1/trading/info/history"
    ]
    
    print("\n[2] 測試 API 端點...")
    
    for endpoint in endpoints:
        url = f"{base_url}{endpoint}"
        response = test_api_endpoint(url, headers)
        
        if response and response.status_code == 200:
            print(f"\n✅ 成功！找到有效端點: {endpoint}")
            break
    
    print("\n" + "=" * 80)
    print("測試完成")
    print("=" * 80)

if __name__ == "__main__":
    main()
