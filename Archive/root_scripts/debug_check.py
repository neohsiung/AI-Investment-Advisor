import os
import sys

# Add src to path
sys.path.append(os.path.abspath('src'))

print("--- Checking Imports ---")
try:
    from src.repositories.verification_repository import AlchemyVerificationRepository
    print("✅ AlchemyVerificationRepository import OK")
except Exception as e:
    print(f"❌ AlchemyVerificationRepository import failed: {e}")

try:
    from src.repositories.verification_repository import VerificationRepository
    print("❌ VerificationRepository (deprecated) STILL EXISTS and importable")
except ImportError:
    print("✅ VerificationRepository (deprecated) import failed as expected")

print("\n--- Checking File/Dir Types ---")
paths_to_check = [
    'client_secret.json',
    'src/client_secret.json',
    'secrets/client_secret.json',
    'src/pages/client_secret.json',
    'src/pages/settings_tabs/client_secret.json'
]

for p in paths_to_check:
    if os.path.exists(p):
        is_dir = os.path.isdir(p)
        print(f"Path: {p} | Exists: True | Is Directory: {is_dir}")
    else:
        print(f"Path: {p} | Exists: False")

print("\n--- Grep check for VerificationRepository in src ---")
os.system("grep -r 'VerificationRepository' src | grep -v 'AlchemyVerificationRepository' | grep -v 'deprecated'")
