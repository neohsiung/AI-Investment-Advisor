# DD-2026-1026 公開歷史舊金鑰的處理：先查還在不在用，再決定換不換
> 一句話：程式不再有任何寫死的 DB 密碼預設值，缺值會明確失敗；歷史上外洩的三個值，由 `scripts/check_leaked_secrets.sh` 比對後，只有「相同」的才依下面的步驟換掉。

**狀態**：程式部分已實作，PR 待補；換金鑰步驟待創辦人執行
**風險級**：R2，移除 fallback、新增檢查腳本；換金鑰步驟屬 R3，動正式環境，只提案，由創辦人核可並執行
**上游**：無 issue；來自 2026-10-26 的公開歷史盤點

## 1 問題：舊做法是什麼、錯在哪
- 舊做法一：公開歷史裡有三個舊值。
  - `src/utils/crypto_utils.py`，96d32f00 加入、817b0453 刪除有一個寫死的 44 字元 Fernet key，在 `MASTER_CRYPTO_KEY` 沒設時當預設。
  - `config/production.env`，96d32f00、edbc0206有一個 28 字元的 `DB_PASS`。
  - `.env.bak-20260711`，3a7be7f0的 `DB_PASS` 是 8 字元，等於程式的預設值。
- 舊做法二：程式把一個公開的字串當 DB 密碼的 fallback，設定漏掉時靜默用它連線，不報錯。
- 證據：
  - `config/production.env` 的 `DB_PASS` 在 96d32f00 與 edbc0206 兩個 commit 內容相同，已用比對確認，沒有印值。
  - 歷史值：`git show 96d32f00:config/production.env`、`git show 3a7be7f0:.env.bak-20260711`、`git show 96d32f00:src/utils/crypto_utils.py`，檢視時請遮住值。
  - crypto_utils 的 key 沒加密過正式資料：`git log --all -S encrypt_secret --oneline` 只有 4 個 commit，全在 `crypto_utils.py` 與它自己的測試，沒有任何程式呼叫過。現行加密用 `LLM_CREDENTIAL_KEY`，`llm_providers.encrypted_api_key`，`FERN:` 前綴與 `APP_SECRET_KEY`，`settings` 表，`ENC:` 前綴。
  - 改動前的 fallback 位置：`src/data/database.py` 三處、`alembic/env.py`、`scripts/init_db.py`、`src/services/llama_index_service.py`、`src/infrastructure/channels/telegram_adapter.py`、`scripts/migrate_line_to_db.py`。
- 受影響範圍的上限：`docker-compose.prod.yml` 的 postgres 只綁 `127.0.0.1:5432`，歷史密碼要有主機存取才能用。這降低風險，不等於可以不查。

## 2 決定：新做法，正本在哪
- 金鑰只走環境變數，`.env` 已 gitignore或金鑰庫。設定檔只放變數名，不放值。缺值明確失敗。
- 不把真值搬進進版控的 config.yml：進版控的檔案會公開在 GitHub，等於再外洩一次。
- 正本：`src/config/db_credentials.py` 的 `require_db_password()`。所有組連線字串的地方都呼叫它；沒設 `DB_PASS`，或舊名 `DB_PASSWORD`就 raise `MissingDbPasswordError`，訊息寫明要設哪個變數。
- 測試與 CI：`tests/conftest.py` 用 `DB_URL=sqlite` 隔離，不碰 DB_PASS；`.github/workflows/ci-cd.yml` 與 `scripts/ci_local.sh` 本來就用環境變數給測試庫密碼，不用改。測試庫是用完即丟的容器，不是正式密碼。
- 不做的事：不改寫 git 歷史；不動 `llm_credential_cipher.py` 的退化行為，見已知殘留；不替正式環境換任何值。

## 3 換金鑰步驟，創辦人在主 checkout 執行，R3
先跑比對，每組只會印「相同／不同／不存在」，不印值。腳本讀不到任何一個歷史值時會報錯並以非零碼結束，不會把讀不到當成「不存在」。
```bash
bash scripts/check_leaked_secrets.sh
```
這支腳本在本 PR 的分支上。合併前，主 checkout 還沒有它，請用：
```bash
ENV_FILE=<主 checkout>/.env bash <本 PR worktree>/scripts/check_leaked_secrets.sh
```
建議先比對、先換完，再讓這份 DD 與 PR 公開，因為 DD 會精確指出哪些 commit 有外洩值。
依結果分支：

**A. 任何一行 DB_PASS 是「相同」**，也就是歷史外洩的密碼仍在用。
1. 備份：`./start.sh backup`，確認 `backups/` 有新的一份。
註：步驟 2 到 4 要連續做完。改完資料庫密碼到 `.env` 與服務重建之間，使用舊密碼的服務會連不上，新連線會被拒絕。
2. 改資料庫內的密碼。`POSTGRES_PASSWORD` 只在資料庫第一次初始化時生效，改環境變數不會改已存在的使用者。用互動式 `psql`，密碼不會出現在指令列或 `ps`：
   `docker exec -it advisor_prod_db psql -U postgres`，進去後執行 `\password postgres`，輸入兩次新密碼。`\password` 送出的是雜湊，不是明文。
3. 把 `.env` 的 `DB_PASS` 改成同一個新值。用編輯器開 `.env`，不要用會留在 shell 歷史的指令貼值。
4. 重建所有讀 `DB_PASS` 的服務，名單用 `grep -n "DB_PASS\|env_file" docker-compose.prod.yml` 列出，目前有 postgres、mcp_server、worker、celery_beat。寫法比照 `start.sh` 的 `PROD_COMPOSE`：
   `docker compose --project-name investment_advisor -f docker-compose.prod.yml $PROFILES up -d --force-recreate postgres mcp_server worker celery_beat`
   `$PROFILES` 沿用 `start.sh:35-41` 的規則：平常是空的；若平常用 `OBSERVABILITY=1 ./start.sh up` 啟動，就填 `--profile observability`，否則 profile 內的服務會被漏掉。
   資料庫的資料在 volume 裡，重建不會重新初始化。postgres 一併重建，是為了讓容器的 `POSTGRES_PASSWORD` 跟 `.env` 一致；不重建的話，重跑檢查腳本時容器那兩列會顯示「相同」，這是預期輸出，不是沒換成功。
5. 驗證：`./start.sh health`。再確認舊密碼已失效：用互動式 `psql` 以舊密碼連線，應該被拒絕。
6. 回滾：新密碼連不上或服務起不來時，把 `.env` 還原成舊 `DB_PASS`，用互動式 `\password postgres` 改回舊值，再用步驟 4 的指令重建；資料沒有動，不需要還原資料庫。`./start.sh restore <id>` 是最後手段。

**B. crypto_utils 的 key 與 `APP_SECRET_KEY` 或 `LLM_CREDENTIAL_KEY` 是「相同」**
1. 備份：`./start.sh backup`。
2. 產生新金鑰：`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`。
3. 新舊金鑰並存於同一個互動 shell 的變數，先乾跑。不要把金鑰寫在指令前綴，那會留在 shell 歷史。先 `set +o history`，再逐個用 `read -rs` 輸入，不回顯，最後 `export`：
   `read -rs APP_SECRET_KEY` `read -rs APP_SECRET_KEY_NEW` `read -rs LLM_CREDENTIAL_KEY` `read -rs LLM_CREDENTIAL_KEY_NEW`，各自獨立執行，再 `export APP_SECRET_KEY APP_SECRET_KEY_NEW LLM_CREDENTIAL_KEY LLM_CREDENTIAL_KEY_NEW`，然後 `python scripts/rotate_encryption_keys.py`。
   用完 `unset` 這四個變數並 `set -o history`。
   只有「相同」的那一把需要換；另一把的 `_NEW` 設成與舊值相同。
4. 乾跑沒有錯誤才加 `--commit`。腳本重新包裝 `settings` 的 `ENC:` 與 `llm_providers` 的 `FERN:` 密文。
5. 之後才把 `.env` 換成新金鑰並重建 mcp_server、worker、celery_beat，指令與 A.4 相同，只是服務名單去掉 postgres：
   `docker compose --project-name investment_advisor -f docker-compose.prod.yml $PROFILES up -d --force-recreate mcp_server worker celery_beat`
   順序不能反：只換 `.env` 會讓資料庫裡的密文變孤兒，而且是靜默失敗，`settings_repository` 的 `_decrypt` 吞掉錯誤並回傳原密文。
6. 驗證：`./start.sh health`；到設定頁確認 eToro 金鑰能讀出，不是 `ENC:` 開頭的字串。
7. 回滾：`--commit` 之後出錯，把 `.env` 還原舊金鑰，用 `./start.sh restore <id>` 還原備份的資料庫。

**C. 兩種比對全部是「不同」或「不存在」**
- 歷史值不是現在在用的值，不用換。crypto_utils 的 key 從未被呼叫過，也沒加密過任何正式資料，所以「不同」時沒有密文需要處理。
- 「不存在」要先排除是路徑或容器名稱錯，`ENV_FILE=`、`DB_CONTAINER=` 可覆寫，再當作「不同」處理。

## 4 可重跑的證明
```bash
cd <worktree> && .venv/bin/python -m pytest tests/unit/config/test_db_credentials.py -q
git grep -nE "(getenv|get)\(\"DB_PASS(WORD)?\", *\"[^\"]+\"\)" -- src alembic scripts services   # 應無輸出
bash -n scripts/check_leaked_secrets.sh
```

## 已知殘留
- `src/services/llm_credential_cipher.py` 在 `LLM_CREDENTIAL_KEY` 缺值時不 raise，退化成只有 base64 的編碼，寫死的 HMAC 字串。正式環境靠 `src/utils/boot_validation.py` 擋啟動。這次不改，另案處理。
- git 歷史不改寫。舊值永遠留在公開歷史，所以只有「換掉仍在用的值」才算處理，刪檔不算。
- `.gitleaksignore` 要等掃描結果，Q2出來再補指紋。
- `scripts/ci_local.sh` 與 CI 的測試庫仍用固定密碼，那是用完即丟的容器，不連正式資料。

## 驗收條件
- AC1：程式裡沒有 DB 密碼的預設值；反驗：在任一處把讀取 `DB_PASS` 的呼叫加回帶字串預設值的寫法，`.claude-task/green.sh` 的全 repo grep 檢查要失敗。
- AC2：缺 `DB_PASS` 時組連線字串會 raise 並寫明變數名；反驗：把 `get_db_engine` 的 `require_db_password()` 改回帶預設值，`test_sync_engine_builder_does_not_use_a_default_password` 要失敗。
- AC3：檢查腳本存在、可執行、語法通過，且本身不含歷史值；反驗：把一個歷史值貼進腳本，`green.sh` 的「腳本不含歷史值」要失敗。
- AC4：腳本執行時不印出任何值；反驗：在主 checkout 跑 `bash scripts/check_leaked_secrets.sh 2>&1 | grep -vE '^(==|--)|: (相同|不同|不存在)$'`，應無任何輸出；有輸出就代表印出了別的東西，要檢查是不是洩漏了值。
- AC5：測試仍通過；反驗：`.venv/bin/python -m pytest tests/unit tests/invariants -q` 全綠；把 `tests/unit/infrastructure/test_telegram_adapter.py` 的 `DB_PASS` 設定拿掉，該檔測試要失敗，證明測試真的依賴明確設定。
