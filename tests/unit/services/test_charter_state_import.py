"""Importing the charter halt service in a fresh interpreter must not depend on import order.
在全新直譯器中匯入章程停機服務，不得依賴匯入順序。"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def _import_ok(statement: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-c", statement], cwd=REPO, capture_output=True, text=True, timeout=120)


def test_charter_state_service_imports_first_in_a_fresh_process():
    r = _import_ok("import src.services.charter_state_service")
    assert r.returncode == 0, r.stderr[-800:]


def test_charter_models_import_first_in_a_fresh_process():
    r = _import_ok("import src.data.charter_models")
    assert r.returncode == 0, r.stderr[-800:]
