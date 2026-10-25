# DD-2026-1025 — 哨兵風險關鍵字改成以詞為單位比對
> 一句話：風險關鍵字要從詞的開頭命中，不再比對字串片段（五個字元以上的英文詞允許詞尾變化，三到四個字元允許 s／es），規則只寫在 `src/domain/keyword_match.py`。

**狀態**：已實作（PR 待補）
**風險級**：R2（哨兵觸發規則；`sentinel_service.py` 在 CODEOWNERS 的 R2 清單）
**上游**：無 issue；來自 2026-10-25 的 LLM 花費盤點

## 1 問題：舊做法是什麼、錯在哪
- 舊做法：`RiskKeyword.score`、`RiskKeywordService.contains_risk`、`score_text` 三處各自用 `keyword in text` 判斷命中，比的是子字串。
- 結果：`es`、`it`、`am`、`ip`、`mu` 這類兩個字母的關鍵字幾乎每則新聞都中。`es` 權重 1.0，單獨就超過觸發門檻 `news_risk_score`（0.6）。
- 證據：2026-10-17～10-23 的 47 場議會裡，44 場由新聞或全球事件觸發，例如 Fortnite 回歸 Apple 的新聞觸發 JPM 議會（關鍵字 `it`、`es`）。這週 LLM 花費約 $2.7，議會佔約 85%，使命預算約每週 $0.96（`config/mission.yaml` 的 `max_llm_usd_per_year`）。
- [推論] 熱門關鍵字的權重會依命中次數往上調（`risk_keyword_service.py` 的 refine 步驟），子字串比對讓短詞命中次數暴增，權重因此升到 1.0，形成迴圈。

## 2 決定：新做法，正本在哪
- 正本：`src/domain/keyword_match.py` 的 `keyword_in_text`。三個呼叫點都改用它（前一個 commit 先做純重構）。
- 規則：
  - 不分大小寫；關鍵字前面緊鄰 ASCII 字母或數字就不算命中（`close` 不再命中 `disclosed`）。
  - 詞尾依長度：≥ `STEM_MIN_LEN`（5）且結尾是英文字母，可接任何字母（`sanction` 命中 `sanctioned`、`bankrupt` 命中 `bankruptcies`）；3–4 個字元允許 `s`／`es`（`war` 命中 `wars`）；更短的只比整詞（`es`、`it`）。
  - 關鍵字前後的空白忽略；空白關鍵字永不命中。
  - 只有 ASCII 字母數字算字元，所以中文關鍵字在中文句子裡照樣命中。
- 不做的事：不改門檻、不改權重、不清關鍵字資料、不動權重調升邏輯。

## 2b Shadow 規則（只記錄，不做決定）
- 候選規則：`keyword_match.shadow_weight`。
  - trends 來源、長度 ≤ `SHADOW_SKIP_TRENDS_MAX_LEN`（4）的關鍵字不計分。它們是熱門股票代號，不是風險詞。
  - 其他關鍵字的單一權重上限 `SHADOW_MAX_SINGLE_WEIGHT`（0.5），低於門檻 0.6，一個關鍵字不能單獨觸發。
- 刻意寫成程式常數，不進 `config/` 或登錄檔：這套規則不做任何決定。切換成正式規則是另一個要審查的變更。
- 記錄點：個股新聞（每個標的一次）、全球事件（每個候選，在過濾器與冷卻之前）、webhook 新聞。計數存在 Redis `sentinel:kw_shadow:<日期>`，保留 35 天，每次記錄一次往返（pipeline）。
- 計數的意思是「在關鍵字階段會觸發」，不是議會場數。之後的過濾器、冷卻、停機閘門對兩套規則一樣。
- shadow 計分不記命中次數，不會回饋到權重調升；記錄失敗只記 WARNING，不影響正式判斷。
- 模擬（只用標題）：上週 44 則觸發候選，shadow 規則只會觸發 1 次。

## 3 後果與部署前提
- 部署後，個股新聞與全球事件兩條路徑的觸發都會變少。下游的全球事件過濾器、冷卻、停機閘門不變。
- `it`、`am` 是真的英文字，整詞比對擋不掉它們，所以光靠這一步只能讓新聞觸發大約減半。

## 4 可重跑的證明
```bash
.venv/bin/python -m pytest tests/unit/domain/test_keyword_match.py -q
```
shadow 一週後的比較：
```bash
docker exec advisor_prod_worker python -c "from src.services.keyword_shadow_recorder import summary; print(summary(7))"
```
看 `*:live` 與 `*:shadow` 的差距，以及 `*:live_only` 的 INFO log（`keyword shadow:` 開頭）裡被 shadow 擋掉的新聞是不是真的該擋。

上週觸發的模擬（只用議會紀錄裡的新聞標題，實際比對還含摘要，所以真實觸發會略高）：子字串 33／44 次，整詞 17／44 次。重跑方式：從 `council_minutes` 匯出 10-17～10-23 的 `topic`，從 `risk_keywords` 匯出啟用中的 `keyword, weight, source`，用 `keyword_in_text` 重新算每則標題的總權重，與 0.6 比較。

## 已知殘留
- 垃圾關鍵字（`es`、`it`、`am` 等）仍在資料表裡，權重仍是 1.0。清理是正式 DB 寫入，另案處理。
- 權重依命中次數調升的迴圈沒動。
- 新規則仍有少量誤報：詞尾放寬讓 `actual` 命中 `actually`、`trade war` 命中 `trade warning`；`es` 複數讓 `war` 命中 `wares`。比子字串少得多，接受。
- shadow 的 `scanned` 只算有抓到新聞的標的；沒有新聞就提早返回，不計數。live 與 shadow 的觸發數仍可直接比較。
- 資料列走 repository 的索引備援路徑時 `source` 是 None（`SELECT *` 欄位順序不可靠），這些列不套 shadow 的 trends 規則。主路徑用欄位名稱取值，不受影響。
- 單靠這一步，估計每週仍約 $1.6，還沒降到 $1。要降到預算內，需要 shadow 規則觀察一週後切換，加上關鍵字清理。

## 驗收條件
- AC1：`es` 不命中 `Names`、`close` 不命中 `disclosed`；反驗：把 `keyword_in_text` 改回 `in`，`test_keyword_inside_another_word_does_not_match` 要失敗。
- AC2：`tariff` 命中 `tariffs`、`sanction` 命中 `sanctioned`、`關稅` 命中中文句子；反驗：拿掉 `_suffix`，`test_plural_of_a_word_of_three_or_more_letters_matches` 與 `test_keyword_of_five_or_more_letters_matches_inflected_forms` 要失敗。
- AC3：三個呼叫點都經過 `keyword_in_text`；反驗：`grep -rn "keyword.lower() in" src` 應無結果。
- AC4：shadow 不改正式判斷、不記命中；反驗：讓 `_analyze_ticker_news` 改用 shadow 分數，或在 shadow 計分裡呼叫 `record_hit`，`test_ticker_news_records_live_hit_and_shadow_miss` 要失敗。
- AC5：Redis 失敗不影響正式分數；反驗：拿掉 `keyword_shadow_recorder.record` 的 try，`test_record_never_raises_when_redis_fails` 要失敗。`keyword_shadow_recorder.compare` 計分時另有一層 try（`test_compare_never_raises_and_records_nothing_when_scoring_fails`），`test_ticker_news_live_score_survives_a_redis_failure` 確認正式分數不變。
