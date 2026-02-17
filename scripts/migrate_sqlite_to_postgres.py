import argparse
import sqlite3
import psycopg2
from psycopg2.extras import execute_values
import json
import logging
from datetime import datetime
from pathlib import Path
import shutil
import os
import uuid

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class LocalMigrator:
    """
    Migrate local SQLite databases to PostgreSQL.
    Aligns with Strategy v4.0 (UUID, JSONB, vector).
    """
    
    def __init__(self, sqlite_paths: list, pg_config: dict):
        self.sqlite_paths = [Path(p) for p in sqlite_paths]
        self.pg_config = pg_config
        self.pg_conn = psycopg2.connect(**pg_config)
    
    def backup_sqlite(self):
        backup_dir = Path("data/backups")
        backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        for path in self.sqlite_paths:
            if path.exists():
                backup_path = backup_dir / f"{path.name}_backup_{timestamp}.db"
                shutil.copy2(path, backup_path)
                logger.info(f"✅ Backup created: {backup_path}")

    def migrate_all(self):
        self.backup_sqlite()
        
        # Table mapping and transformation rules
        for sqlite_path in self.sqlite_paths:
            if not sqlite_path.exists(): continue
            logger.info(f"--- Migrating {sqlite_path} ---")
            conn = sqlite3.connect(str(sqlite_path))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
            tables = [row[0] for row in cursor.fetchall()]
            
            for table in tables:
                logger.info(f"📦 Table: {table}")
                cursor.execute(f"SELECT * FROM {table}")
                rows = cursor.fetchall()
                if not rows: continue
                
                columns = [desc[0] for desc in cursor.description]
                transformed_rows = []
                for row in rows:
                    transformed_row = self._transform_row(table, dict(row))
                    transformed_rows.append(tuple(transformed_row.values()))
                
                pg_cursor = self.pg_conn.cursor()
                placeholders = ','.join(['%s'] * len(columns))
                # Use standard standard column names from SQLite
                insert_query = f"INSERT INTO {table} ({','.join(columns)}) VALUES %s ON CONFLICT DO NOTHING"
                
                try:
                    execute_values(pg_cursor, insert_query, transformed_rows)
                    self.pg_conn.commit()
                    logger.info(f"  ✅ Migrated {len(transformed_rows)} rows")
                except Exception as e:
                    self.pg_conn.rollback()
                    logger.error(f"  ❌ Failed {table}: {e}")
            conn.close()

    def _transform_row(self, table_name, row):
        # Handle UUID migration if incoming ID is not UUID
        if 'id' in row and row['id']:
            try:
                uuid.UUID(row['id'])
            except ValueError:
                # If not UUID, we keep as TEXT for now if DB allows, 
                # or generate new one. But typically keeping original is better for FKs.
                pass
        
        if table_name == 'memory_embeddings':
            if 'embedding' in row and row['embedding'] and isinstance(row['embedding'], str):
                try:
                    row['embedding'] = json.loads(row['embedding'])
                except:
                    pass
            if 'metadata' in row and row['metadata'] and isinstance(row['metadata'], str):
                try:
                    row['metadata'] = json.loads(row['metadata'])
                except:
                    pass
        elif table_name == 'transactions':
            # Ensure trade_date is a valid date string or date object
            pass
        
        # Ensure all dict/list fields are handled for Postgres JSONB
        for key, value in row.items():
            if isinstance(value, str) and (value.startswith('{') or value.startswith('[')):
                try:
                    row[key] = json.loads(value)
                except:
                    pass
        return row

    def close(self):
        self.pg_conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--sqlite-paths', nargs='+', default=['data/portfolio.db', 'data/memory.db', 'data/cache.db'])
    parser.add_argument('--pg-url', help='Postgres URL or use env vars')
    args = parser.parse_args()
    
    pg_config = {
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': os.getenv('DB_PORT', '5432'),
        'database': os.getenv('DB_NAME', 'portfolio'),
        'user': os.getenv('DB_USER', 'postgres'),
        'password': os.getenv('DB_PASS', 'postgres')
    }
    
    migrator = LocalMigrator(args.sqlite_paths, pg_config)
    migrator.migrate_all()
    migrator.close()
