#!/usr/bin/env python3
"""
Quick diagnostic - call all frontend API endpoints and report status
"""
import requests

BASE = "http://localhost:8000"

# Use correct user (supermfb@gmail.com in Postgres)
from src.utils.jwt_utils import create_access_token
token = create_access_token({"sub": "90693c07-6177-42df-97d9-915f3ce7c573", "email": "supermfb@gmail.com"})
headers = {"Authorization": f"Bearer {token}"}

endpoints = [
    # Command Center / Dashboard
    ("GET", "/api/v1/dashboard/summary"),
    ("GET", "/api/v1/dashboard/positions"),
    ("GET", "/api/v1/dashboard/agents"),
    ("GET", "/api/v1/dashboard/intelligence"),
    ("GET", "/api/v1/dashboard/alerts"),
    # 績效分析 / Performance
    ("GET", "/api/v1/dashboard/performance/history"),
    ("GET", "/api/v1/dashboard/performance/agents"),
    # 分析報告 / Reports
    ("GET", "/api/v1/dashboard/reports"),
    # 設定 / Settings
    ("GET", "/api/v1/settings"),
    # Transactions
    ("GET", "/api/v1/transactions"),
]

print(f"\n{'=' * 70}")
print(f"  API DIAGNOSTIC REPORT")
print(f"{'=' * 70}")
print(f"  Token user: supermfb@gmail.com (UUID: 65b548cf-...)")
print(f"{'=' * 70}\n")

for method, path in endpoints:
    url = f"{BASE}{path}"
    try:
        r = requests.request(method, url, headers=headers, timeout=10)
        body = r.json()
        status = r.status_code
        if status == 200:
            data = body.get("data", body)
            if isinstance(data, list):
                summary = f"{len(data)} items"
            elif isinstance(data, dict):
                summary = f"{len(data)} keys: {list(data.keys())[:4]}"
            else:
                summary = str(data)[:80]
            print(f"  ✅ {status} {path}")
            print(f"       └─ {summary}")
        else:
            detail = body.get("detail", str(body)[:100])
            print(f"  ❌ {status} {path}")
            print(f"       └─ {detail}")
    except requests.exceptions.RequestException as e:
        print(f"  💀 CONN_ERR {path}: {e}")
    print()
