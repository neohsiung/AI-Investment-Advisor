"""resolve_within must reject anything that leaves the base directory."""
import os

import pytest

from src.utils.safe_path import resolve_within


def test_inside_ok(tmp_path):
    assert resolve_within(tmp_path, "a.yaml") == os.path.realpath(tmp_path / "a.yaml")


@pytest.mark.parametrize("bad", ["../x.yaml", "a/../../x", "/etc/passwd", "..", "sub/../../x"])
def test_escape_rejected(tmp_path, bad):
    with pytest.raises(ValueError):
        resolve_within(tmp_path, bad)


def test_sibling_prefix_rejected(tmp_path):
    base = tmp_path / "wf"
    base.mkdir()
    (tmp_path / "wf-evil").mkdir()
    with pytest.raises(ValueError):
        resolve_within(base, "../wf-evil/x")


def test_symlink_escape_rejected(tmp_path):
    base = tmp_path / "wf"
    base.mkdir()
    (base / "link").symlink_to(tmp_path)
    with pytest.raises(ValueError):
        resolve_within(base, "link/secret")


def test_pdf_ingest_rejects_outside_root(tmp_path, monkeypatch):
    import asyncio
    from unittest.mock import MagicMock
    from src.services.llama_index_service import LlamaIndexService

    monkeypatch.setenv("RAG_INGEST_ROOT", str(tmp_path))
    svc = LlamaIndexService.__new__(LlamaIndexService)
    svc._pdf_reader = MagicMock()
    with pytest.raises(ValueError):
        asyncio.run(svc.ingest_pdf("/etc/hosts", "AAPL", "report", "c"))
    svc._pdf_reader.load_data.assert_not_called()
