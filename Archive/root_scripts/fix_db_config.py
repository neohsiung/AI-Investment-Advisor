#!/usr/bin/env python3
"""
修正資料庫配置並確保使用 PostgreSQL
Fix database configuration to ensure PostgreSQL is used
"""

import os
import sys

# Force PostgreSQL configuration
os.environ['DB_TYPE'] = 'postgres'
os.environ['DB_HOST'] = 'localhost'  # Override 'postgres' hostname
os.environ['DB_USER'] = 'postgres'
os.environ['DB_PASS'] = 'postgres'
os.environ['DB_NAME'] = 'portfolio'
os.environ['DB_PORT'] = '5432'

from src.data.database import get_db_connection, init_db
from sqlalchemy import text
import uuid

print("=" * 60)
print("資料庫配置修正工具")
print("=" * 60)

# Test connection
print("\n[1] 測試 PostgreSQL 連接...")
try:
    conn = get_db_connection()
    result = conn.execute(text("SELECT version()")).fetchone()
    print(f"✅ PostgreSQL 連接成功")
    print(f"   版本: {result[0][:50]}...")
    conn.close()
except Exception as e:
    print(f"❌ PostgreSQL 連接失敗: {e}")
    print("\n請確認:")
    print("1. PostgreSQL 服務正在運行")
    print("2. 連接資訊正確 (localhost:5432)")
    sys.exit(1)

# Initialize database
print("\n[2] 初始化資料庫結構...")
try:
    init_db()
    print("✅ 資料庫結構初始化完成")
except Exception as e:
    print(f"⚠️  資料庫可能已存在: {e}")

# Check and create supermfb@gmail.com user
print("\n[3] 檢查使用者...")
conn = get_db_connection()

email = 'supermfb@gmail.com'
result = conn.execute(text('SELECT id, email FROM users WHERE email = :email'), {'email': email}).fetchone()

if result:
    user_id = result[0]
    print(f"✅ 使用者已存在: {email}")
    print(f"   User ID: {user_id}")
else:
    user_id = str(uuid.uuid4())
    conn.execute(text(
        'INSERT INTO users (id, email, name, preferences, metadata) VALUES (:id, :email, :name, :prefs::jsonb, :meta::jsonb)'
    ), {
        'id': user_id,
        'email': email,
        'name': 'Super MFB',
        'prefs': '{}',
        'meta': '{}'
    })
    
    conn.execute(text(
        'INSERT INTO user_identities (id, user_id, provider, identifier, is_primary) VALUES (:id, :uid, :prov, :ident, :prim)'
    ), {
        'id': str(uuid.uuid4()),
        'uid': user_id,
        'prov': 'email',
        'ident': email,
        'prim': 1
    })
    
    conn.commit()
    print(f"✅ 已建立使用者: {email}")
    print(f"   User ID: {user_id}")

# Test settings insertion
print("\n[4] 測試設定儲存...")
try:
    conn.execute(text(
        'INSERT INTO settings (user_id, key, value) VALUES (:uid, :key, :value) '
        'ON CONFLICT (user_id, key) DO UPDATE SET value = EXCLUDED.value'
    ), {'uid': user_id, 'key': 'test_config_fix', 'value': '"success"'})
    conn.commit()
    print(f"✅ 設定儲存成功 (user_id: {user_id[:8]}...)")
except Exception as e:
    print(f"❌ 設定儲存失敗: {e}")

# Show all users
print("\n[5] 當前使用者列表...")
result = conn.execute(text('SELECT id, email, name FROM users ORDER BY email')).fetchall()
print(f"總共 {len(result)} 個使用者:")
for user in result:
    print(f"  - {user[1]} ({user[2] if user[2] else 'N/A'}) | ID: {user[0][:8]}...")

conn.close()

print("\n" + "=" * 60)
print("✅ 資料庫配置修正完成")
print("=" * 60)
print("\n提示:")
print("1. 所有腳本都應該設定 DB_HOST=localhost（而非 postgres）")
print("2. 使用者 ID 是 UUID，不是 email")
print("3. Settings 儲存時應使用 UUID 作為 user_id")
