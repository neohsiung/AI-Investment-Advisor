import os
import uuid
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

db_url = os.getenv("DB_URL")
engine = create_engine(db_url)
user_id = '90693c07-6177-42df-97d9-915f3ce7c573'

identities = [
    ('email', 'supermfb@gmail.com'),
    ('line', 'U89230a0a471836b5533901492ed503bc'),
    ('telegram', '982605706')
]

print(f"Backfilling identities for user: {user_id}")

with engine.begin() as conn:
    for provider, ident in identities:
        if not ident:
            continue
        # Use ON CONFLICT to avoid duplicates
        conn.execute(text("""
            INSERT INTO user_identities (id, user_id, provider, identifier, is_primary) 
            VALUES (:id, :uid, :prov, :ident, :primary) 
            ON CONFLICT (provider, identifier) DO UPDATE SET user_id = EXCLUDED.user_id, is_primary = EXCLUDED.is_primary
        """), {
            "id": str(uuid.uuid4()),
            "uid": user_id,
            "prov": provider,
            "ident": ident,
            "primary": 1 if provider == 'email' else 0
        })
        print(f"  - {provider}: {ident}")

print("Backfill complete.")
