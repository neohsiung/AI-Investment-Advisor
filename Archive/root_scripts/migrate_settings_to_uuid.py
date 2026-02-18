#!/usr/bin/env python3
"""
遷移 settings 表中的 email user_id 到 UUID
Migrate settings table from email user_id to UUID
"""

import os
os.environ['DB_TYPE'] = 'postgres'
os.environ['DB_HOST'] = 'localhost'
os.environ['DB_USER'] = 'postgres'
os.environ['DB_PASS'] = 'postgres'
os.environ['DB_NAME'] = 'portfolio'

from src.data.database import get_db_connection
from sqlalchemy import text

def migrate_settings():
    """
    遷移所有使用 email 作為 user_id 的設定到正確的 UUID
    """
    conn = get_db_connection()
    
    print("=" * 80)
    print("Settings 遷移工具：Email → UUID")
    print("=" * 80)
    
    # Find all settings with email as user_id
    result = conn.execute(text(
        "SELECT DISTINCT user_id FROM settings WHERE user_id LIKE '%@%'"
    )).fetchall()
    
    email_user_ids = [row[0] for row in result]
    
    if not email_user_ids:
        print("\n✅ 沒有需要遷移的設定")
        conn.close()
        return
    
    print(f"\n找到 {len(email_user_ids)} 個使用 email 的 user_id:")
    for email in email_user_ids:
        print(f"  - {email}")
    
    print("\n開始遷移...")
    
    migrated_count = 0
    skipped_count = 0
    
    for email in email_user_ids:
        # Find the corresponding UUID
        user_result = conn.execute(text(
            "SELECT id FROM users WHERE email = :email"
        ), {'email': email}).fetchone()
        
        if not user_result:
            print(f"\n⚠️  跳過 {email}: 在 users 表中找不到對應的使用者")
            skipped_count += 1
            continue
        
        uuid = user_result[0]
        
        # Get all settings for this email
        settings = conn.execute(text(
            "SELECT key, value FROM settings WHERE user_id = :email"
        ), {'email': email}).fetchall()
        
        print(f"\n處理 {email} → {uuid}")
        print(f"  找到 {len(settings)} 個設定")
        
        for key, value in settings:
            try:
                # Check if setting already exists for UUID
                existing = conn.execute(text(
                    "SELECT value FROM settings WHERE user_id = :uuid AND key = :key"
                ), {'uuid': uuid, 'key': key}).fetchone()
                
                if existing:
                    print(f"    跳過 {key}: UUID 已有此設定")
                else:
                    # Insert with UUID
                    conn.execute(text(
                        "INSERT INTO settings (user_id, key, value) VALUES (:uuid, :key, :value)"
                    ), {'uuid': uuid, 'key': key, 'value': value})
                    print(f"    ✓ 遷移 {key}")
                    migrated_count += 1
                    
            except Exception as e:
                print(f"    ✗ 錯誤 {key}: {e}")
        
        # Delete old email-based settings
        try:
            conn.execute(text(
                "DELETE FROM settings WHERE user_id = :email"
            ), {'email': email})
            print(f"  ✓ 刪除舊的 email-based 設定")
        except Exception as e:
            print(f"  ✗ 刪除失敗: {e}")
    
    conn.commit()
    conn.close()
    
    print("\n" + "=" * 80)
    print(f"遷移完成！")
    print(f"  遷移: {migrated_count} 個設定")
    print(f"  跳過: {skipped_count} 個使用者")
    print("=" * 80)

if __name__ == "__main__":
    migrate_settings()
