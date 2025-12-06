import os
import sys

# Add project root to path to allow importing src
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import sqlite3
import pandas as pd
from sqlalchemy import create_engine, text
from src.database import get_db_engine

import argparse

def migrate_data(source_db_path="data/portfolio.db"):
    if not os.path.exists(source_db_path):
        print(f"Source SQLite database not found at {source_db_path}. Nothing to migrate.")
        return

    print(f"Starting migration from {source_db_path} to PostgreSQL...")
    
    # 1. Connect to SQLite
    sqlite_conn = sqlite3.connect(source_db_path)
    
    # 2. Connect to PostgreSQL (Target)
    # Ensure DB_TYPE is postgres or manual connection string
    # We assume env vars are set or we force it here if needed, but let's rely on get_db_engine
    # But get_db_engine logic depends on DB_TYPE.
    # We should explicitly check if we can connect to Postgres.
    
    # Check if we are in Postgres mode
    if os.getenv("DB_TYPE") != "postgres":
        print("Warning: DB_TYPE is not set to 'postgres'. Please set DB_TYPE=postgres, DB_HOST, DB_USER, DB_PASS, DB_NAME.")
        # We can try to proceed if user wants to just load into whatever get_db_engine returns, 
        # but if it returns SQLite engine (same as source), it's pointless.
        # But we can pass different params to get_db_engine? No, it uses env vars.
        # So we must assume user sets env vars.
    
    pg_engine = get_db_engine()
    
    # Verify target is Postgres
    if pg_engine.dialect.name != 'postgresql':
        print(f"Target database engine is {pg_engine.dialect.name}. Expecting 'postgresql'. Aborting.")
        return

    tables = ["transactions", "cash_flows", "daily_snapshots", "settings", "scheduler_logs", "prompt_history", "reports", "recommendations"]
    
    try:
        with pg_engine.connect() as pg_conn:
            for table in tables:
                print(f"Migrating table: {table}...")
                try:
                    # Read from SQLite
                    df = pd.read_sql(f"SELECT * FROM {table}", sqlite_conn)
                    
                    if df.empty:
                        print(f"  Table {table} is empty. Skipping.")
                        continue
                        
                    # Write to Postgres
                    # Use 'append' method. If table doesn't exist, it might fail if we depend on init.sql
                    # But init.sql should have run.
                    # We might need to handle duplicates? 'replace' drops table, we don't want that if init.sql set up constraints.
                    # 'append' is best. We should probably clear target table first?
                    # valid option: if_exists='append'
                    
                    # For safety, let's clear target table
                    pg_conn.execute(text(f"TRUNCATE TABLE {table} CASCADE")) 
                    # CASCADE might be needed if foreign keys exist (none currently)
                    
                    df.to_sql(table, pg_engine, if_exists='append', index=False)
                    print(f"  Migrated {len(df)} rows.")
                    
                except Exception as e:
                    print(f"  Error migrating table {table}: {e}")
                    
            print("Migration completed successfully.")
            
    except Exception as e:
        print(f"Migration failed: {e}")
    finally:
        sqlite_conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate data from SQLite to PostgreSQL")
    parser.add_argument("--source", default="data/portfolio.db", help="Path to source SQLite database file")
    parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")
    args = parser.parse_args()

    if not args.yes:
        confirm = input(f"This will overwrite data in the configured PostgreSQL database with data from {args.source}. Continue? (y/n): ")
        if confirm.lower() != 'y':
            print("Migration cancelled.")
            exit(0)
            
    migrate_data(args.source)
