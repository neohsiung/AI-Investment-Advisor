---
name: ci-test
description: |
  預提交檢查工具，包含測試覆蓋率、安全掃描、Wiki 完整性與授權合規性。
  觸發時機：(1) 任何 git commit 前
  (2) 移除任何 pip 套件（requirements.txt）後
  (3) 重構任何 import 路徑或模組結構後
  (4) CI 回報 coverage 低於門檻或 collection error 時
---

# CI Test (Pre-Commit Check)

> 本技能為 **Agent Dev Skill**，用於在執行 `git commit` 前，確保程式碼品質與安全性符合專案要求。

## 適用時機 (When to Use)

- **在任何 `git commit` 前**：確保本次變更沒有破壞現有測試、引入安全漏洞或破壞 Wiki 連結。
- **當 Agent 完成一個階段性的功能開發或重構時**。
- **CodeQL / Dependabot 回報新警告時**：選取相關廢棄的 `src/` 路徑，執行全面 taint 掃描（參考 `agent-secret-redaction` 技能）再 commit 修復。
- **Health check 測試失敗**：若 CI 回報 `/health` endpoint 狀態不是 `healthy`，必須檢查該測試是否有 mock DB（詳見下方）。

## 核心測試項目 (Core Test Items)

1. **Test Collection Dry-Run（必做，優先於所有其他步驟）**：確認所有測試可被正確 import，無 `ImportError` / `ModuleNotFoundError`。
   ```bash
   python3 -m pytest --collect-only -q 2>&1 | grep -E "ERROR|ImportError|ModuleNotFoundError"
   # 必須零輸出，否則禁止 commit
   ```
   > ⚠️ 特別注意：在移除任何套件或重構 import 路徑後，**必須**執行此步驟。

2. **Run tests with coverage**: 執行 `pytest --cov=src`，確保新代碼有足夠的測試覆蓋。
   - **增量模式 (Default)**: 僅執行與變更檔案相關的單元測試，不生成全量覆蓋率。
   - **完整模式 (--full)**: 執行全量測試與覆蓋率報告。
   - **CI 門檻（動態讀取，勿 hardcode）**：
     ```bash
     CI_THRESHOLD=$(grep "cov-fail-under" .github/workflows/*.yml | grep -oP '\d+' | head -1)
     echo "CI coverage threshold: ${CI_THRESHOLD}%"
     pytest --cov=src --cov-fail-under=${CI_THRESHOLD} tests/unit/
     ```
3. **Security Scan (Bandit & Grep Checks)**: 執行 `bandit` 掃描，增量模式僅掃描變更檔案。
4. **Wiki Integrity Check (Flat-Linking)**: 驗證 Wiki 內部連結的有效性，確保遵循扁平化連結規範。
5. **License Compliance Check**: 檢查第三方套件的授權合規性。

## 使用指南 (Usage Guide)

Agent 應在準備 commit 前執行一鍵檢查腳本：

```bash
# 1. 執行增量檢查 (預設，推動原子提交)
python .agent/skills/ci-test/scripts/ci_test.py

# 2. 執行全量檢查 (發布前或重大變更)
python .agent/skills/ci-test/scripts/ci_test.py --full
```

### 測試與覆蓋率 (Coverage Checks)

```bash
# 1. 執行並輸出缺失行號
pytest --cov=src --cov-report=term-missing

# 2. 快速抓出低於 75% 的模組
pytest --cov=src --cov-report=term tests/ | awk '$NF < 75 {print}'
```

**優先覆蓋目標**：

- `P0`: Services 層 (> 80%)，錯誤處理 (100%)
- `P1`: Repositories (> 75%)，Agents (> 70%)

### 安全與依賴項掃描 (Security Audits)

```bash
# 1. Bandit 代碼掃描 (重點檢查 B324, B608)
bandit -r src/

# 2. 依賴項漏洞審查
safety check -r requirements.txt
pip-audit -r requirements.txt

# 3. 硬編碼與潛在風險檢查
grep -r "os.getenv" src/ | grep -vE "test_|conftest"
grep -r "hashlib.md5" src/
grep -r "execute(f\"" src/
grep -rE "(key|token|password|secret)\s*=\s*['\"][a-zA-Z0-9]{10,}['\"]" src/
```

### Wiki 檢查

```bash
python .agent/skills/wiki-maintainer/scripts/verify_wiki_links.py
```

### 授權檢查

```bash
pip-licenses
```

## 注意事項 (Precautions)

- 若任何一項檢查失敗，**嚴禁執行 commit**，必須先修復問題。
- 對於 Bandit 的警告，若確認為 False Positive，應使用 `# nosec` 標註而非直接忽略。
- Wiki 連結若失效，應參考 `wiki-maintainer` 技能進行修復。

## Health Check 測試與 CI 隱離 (Health Check Test & CI DB Isolation)

> CI 環境無實題 DB，若 `/health` endpoint 內部是這樣的模式：
> `status = 'healthy' if db.ping() else 'degraded'`
> 則測試必須 mock `db.ping()` ，否則 CI 永遠回報 `degraded`。

```python
# 測試檔式範例：health check endpoint 必須 mock DB 依賴
@pytest.mark.asyncio
async def test_health():
    with patch("services.mcp_server.src.app.asyncpg.connect", new_callable=AsyncMock) as mock_conn:
        mock_conn.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
        mock_conn.return_value.__aexit__ = AsyncMock(return_value=False)
        async with AsyncClient(app=app, base_url="http://test") as ac:
            resp = await ac.get("/health")
        assert resp.json()["status"] == "healthy"
```

**判斷準則**：若 health 測試失敗且錯誤為 `assert 'degraded' == 'healthy'`，佄必是 DB mock 缺失，而非业務邏輯錯誤。
