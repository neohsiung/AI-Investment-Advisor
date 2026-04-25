#!/usr/bin/env python3
"""
v11.1 Encryption Migration Script
--------------------------------
This script migrates existing sensitive settings (API keys, secrets) 
from plain text to encrypted format using Fernet symmetric encryption.
"""

import os
import sys
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from dotenv import load_dotenv
load_dotenv()

from src.repositories.settings_repository import AlchemySettingsRepository
from src.data.models import Setting
from src.data.database import get_db_engine

def run_migration():
    print("🚀 Starting Encryption Migration (Phase 11)...")
    
    auth_key = os.getenv("APP_SECRET_KEY")
    if not auth_key:
        print("❌ ERROR: APP_SECRET_KEY not found in environment.")
        print("Please generate one and add it to your .env file first.")
        sys.exit(1)
        
    repo = AlchemySettingsRepository(get_db_engine())
    session = repo.session
    
    try:
        # Find all settings
        all_settings = session.query(Setting).all()
        migrated_count = 0
        total_count = len(all_settings)
        
        print(f"📊 Scanning {total_count} settings...")
        
        for setting in all_settings:
            # Check if it should be encrypted
            if repo._should_encrypt(setting.key):
                # Check if it's already encrypted
                val = setting.value
                if isinstance(val, str) and val.startswith("ENC:"):
                    # Already encrypted, skip
                    continue
                
                print(f"🔒 Encrypting key: {setting.key} (User: {setting.user_id})")
                
                # Use the repository's internal encryption method
                setting.value = repo._encrypt(val)
                migrated_count += 1
        
        if migrated_count > 0:
            session.commit()
            print(f"✅ SUCCESS: Migrated {migrated_count} settings to encrypted format.")
        else:
            print("✨ No plain-text sensitive settings found. System is already clean.")
            
    except Exception as e:
        session.rollback()
        print(f"❌ ERROR: Migration failed. {str(e)}")
        sys.exit(1)
    finally:
        repo.close_session()

if __name__ == "__main__":
    run_migration()
