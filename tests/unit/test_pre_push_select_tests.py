"""
Selector for the pre-push fast regression step maps changed paths to test files.
pre-push 快速回歸步驟的選測器：把變更路徑對應到測試檔。
"""

from pathlib import Path

from scripts.pre_push_select_tests import MAX_FILES, select_tests


def _touch(root: Path, *rels: str) -> None:
    for rel in rels:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("")


def test_src_file_maps_to_matching_tests(tmp_path):
    _touch(
        tmp_path,
        "src/services/foo_service.py",
        "tests/unit/services/test_foo_service.py",
        "tests/unit/services/test_foo_service_extra.py",
        "tests/unit/services/test_bar.py",
    )
    got = select_tests(["src/services/foo_service.py"], tmp_path)
    assert got == [
        "tests/unit/services/test_foo_service.py",
        "tests/unit/services/test_foo_service_extra.py",
    ]


def test_changed_test_file_selected_directly(tmp_path):
    _touch(tmp_path, "tests/unit/core/test_x.py")
    assert select_tests(["tests/unit/core/test_x.py"], tmp_path) == [
        "tests/unit/core/test_x.py"
    ]


def test_deleted_or_missing_and_non_python_ignored(tmp_path):
    _touch(tmp_path, "tests/unit/test_keep.py")
    got = select_tests(
        [
            "tests/unit/test_gone.py",  # deleted in the diff
            "src/services/no_tests_here.py",
            "docs/readme.md",
            "src/__init__.py",
            "tests/unit/conftest.py",
        ],
        tmp_path,
    )
    assert got == []


def test_invariants_and_config_not_duplicated(tmp_path):
    # Always-run dirs are handled by the shell; selector must not re-add them.
    # 固定必跑的目錄由 shell 處理，選測器不重複加入。
    _touch(
        tmp_path,
        "tests/invariants/test_a.py",
        "tests/unit/config/test_b.py",
        "tests/unit/test_fail_silent_policy.py",
    )
    got = select_tests(
        [
            "tests/invariants/test_a.py",
            "tests/unit/config/test_b.py",
            "tests/unit/test_fail_silent_policy.py",
        ],
        tmp_path,
    )
    assert got == []


def test_dedupe_sorted_and_capped(tmp_path):
    names = [f"tests/unit/test_m{i:03d}.py" for i in range(MAX_FILES + 15)]
    _touch(tmp_path, *names)
    got = select_tests(list(reversed(names)) + names[:3], tmp_path)
    assert len(got) == MAX_FILES
    assert got == sorted(set(got))


def test_real_repo_sample():
    root = Path(__file__).resolve().parents[2]
    got = select_tests(["src/services/webhook_service.py"], root)
    assert all(g.startswith("tests/") and "test_webhook_service" in g for g in got)
