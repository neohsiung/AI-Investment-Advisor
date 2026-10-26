# DD-2026-1026 Telegram webhook 要驗 Secret Token
> 一句話：webhook 現在只靠請求內容裡的 chat_id 認人，而 chat_id 出現在公開歷史；提案在 `setWebhook` 設 `secret_token`，處理前先驗標頭，並讓 `/resume` 多一道確認。

**狀態**：提案，等創辦人核可；本 PR 不改任何程式
**風險級**：R3，由創辦人核可並執行。`/resume` 會把總開關 `ai_trading_enabled` 寫成 true，屬動錢路徑。
**上游**：無 issue；來自 2026-10-26 的公開歷史盤點

## 1 問題：舊做法是什麼、錯在哪
- 認人方式：`src/services/webhook_service.py:503-552` 的 `telegram_bot_webhook` 從 payload 取出 `chat_id`，第 546 行用 `find_user_by_channel_id(chat_id)` 對應到使用者；對得上就當成本人。程式沒有檢查 Telegram 送來的 `X-Telegram-Bot-Api-Secret-Token` 標頭，整個檔案搜不到 `secret_token`。
- 路由經由隧道對外：`infra/nginx/nginx.conf` 的 8080 虛擬主機專供 ngrok，只轉 `/webhook/` 與 `/callback/`，所以 `/webhook/telegram` 是從網際網路可達的入口。另外 `src/api/middleware/local_auth.py:38` 的 `_ALWAYS_OPEN_PREFIXES` 含 `/webhook`，即使 `AUTH_MODE=token` 也不要求 token，所以 `/webhook/telegram` 只剩 payload 這一道門。同檔的一般 webhook 會驗 `X-API-Key`，`webhook_service.py:191-194`，Telegram 這條沒有。
- 能做什麼：`/resume` 在 `webhook_service.py:856-861` 把 `ai_trading_enabled` 寫成 `true`；`/pause` 在 850 行寫成 `false`；另有按鈕回呼 `resume_trading`，`webhook_service.py:608` 起，實作在 `src/services/actionable_alert_service.py:370`做同一件事。
- 為什麼 chat_id 不是祕密：它出現在公開歷史，`3a7be7f0` 的 `.env.bak-20260711` 有 `TELEGRAM_CHAT_ID`。本文不寫值。任何人取得它，再知道這個服務的 webhook 網址，就能偽造一個看起來來自本人的請求。網址是否外洩由創辦人自行判斷，本文不記錄。
- 現有緩解：開關要真的下單還要過風控閘門與資本上限，`/resume` 本身不會下單。這降低損失上限，但不是驗證。

## 2 決定：新做法，正本在哪
- 正本：Telegram Bot API 的 `setWebhook` 參數 `secret_token`。設了之後，Telegram 每次呼叫都帶 `X-Telegram-Bot-Api-Secret-Token` 標頭，值等於設定的字串。
- 提案一，註冊時設定：`src/setup_telegram_webhook.py` 的 `setWebhook` 請求加 `secret_token`，值從環境變數 `TELEGRAM_WEBHOOK_SECRET` 讀；沒設就拒絕註冊並說明，不產生預設值。Telegram 規定 1 到 256 個字元，限 `A-Z a-z 0-9 _ -`。
- 提案二，處理前驗證：`telegram_bot_webhook` 在讀 payload 之前先比對標頭與環境變數，用常數時間比較。標頭缺少或不符，回 401 並且不處理、不查使用者；伺服器端沒設 `TELEGRAM_WEBHOOK_SECRET` 時也回 401，並記一筆 error 層級 log。這是關著門的預設，不是放行的預設。
- 提案三，`/resume` 再加一道確認：收到 `/resume` 先回一則帶按鈕的訊息，確認後才寫 true；確認動作帶一次性、短時效的 token。`resume_trading` 按鈕回呼同樣要經過這一道。`/pause` 維持一步完成，因為它把風險降低。
- 金鑰處理：`TELEGRAM_WEBHOOK_SECRET` 只走環境變數或金鑰庫，不寫進任何進版控的檔案；新增到 `.env.example` 時只放變數名與空值，並同步 `src/config/env.py` 的宣告，讓 `tests/unit/config/test_env_documented.py` 通過。
- 不做的事：不改 chat_id 對應邏輯；不移除 `/webhook` 的公開前綴，因為其他 webhook 靠它；不寫出正式環境網域或任何值。

## 3 部署順序與回滾
1. 先設定環境變數 `TELEGRAM_WEBHOOK_SECRET`，再部署程式並重建 api。
2. 立刻執行 `setup_telegram_webhook.py` 重新註冊，帶上 `secret_token`，並帶 `drop_pending_updates=true`，避免 401 期間累積的 `/resume` 等指令事後被重放。
3. 用 `/status` 驗證通了。
兩步之間 Telegram 的指令會回 401，包括 `/pause`；這段期間只能從本機儀表板暫停交易。這段時間越短越好。
回滾：還原程式並在 Telegram 端重新 `setWebhook`，不帶 `secret_token`即可，沒有資料變更。

## 4 可重跑的證明
現況沒有驗證，下面這條現況無輸出，改完要有輸出：
```bash
git grep -n -i "secret.token" -- src/services/webhook_service.py src/setup_telegram_webhook.py
```

行為層證明由實作 PR 補，指令固定為：
```bash
.venv/bin/python -m pytest tests/unit/services/test_webhook_telegram_secret.py -q
```
測試要涵蓋：標頭缺少、標頭錯誤、伺服器沒設密鑰，三種都回 401 且 `find_user_by_channel_id` 沒被呼叫；標頭正確才進入處理。

## 已知殘留
- chat_id 已在公開歷史，無法收回。驗證標頭之後它不再單獨構成授權，但仍建議視為已知資訊。
- 驗證依賴 `secret_token` 不外洩。它只存在於伺服器環境變數與 Telegram 端，輪換方式是改環境變數後重跑註冊。
- 一般 webhook 的 `X-API-Key` 驗證沒有檢查，本 DD 不處理。
- `/resume` 的確認機制需要選一種一次性 token 的存放，例如 Redis 加短 TTL，實作時再定。

## 驗收條件
- AC1：沒有標頭、標頭錯誤、或伺服器沒設密鑰時，`POST /webhook/telegram` 回 401，且不查使用者、不寫任何設定；反驗：把驗證那一段拿掉，三個 401 測試要失敗。
- AC2：標頭正確時照原行為處理；反驗：用正確標頭送 `/status`，要得到回覆；把比對寫反，這個測試要失敗。
- AC3：`setup_telegram_webhook.py` 沒有 `TELEGRAM_WEBHOOK_SECRET` 時拒絕註冊；反驗：清掉該環境變數執行，要以非零碼結束並說明原因。
- AC4：`/resume` 與 `resume_trading` 按鈕在確認前不寫 `ai_trading_enabled`；反驗：送 `/resume` 不按確認，資料庫的值不變；拿掉確認步驟，這個測試要失敗。
- AC5：密鑰比對是常數時間；反驗：`git grep -n "compare_digest" -- src/services/webhook_service.py` 要有輸出，改成 `==` 後這條檢查要失敗。
- AC6：文件與範例檔不含任何值；反驗：`git grep -n "TELEGRAM_WEBHOOK_SECRET" -- .env.example` 只出現變數名，且 `tests/unit/config/test_env_documented.py` 通過。
