# DD-2026-1025 — 哨兵風險關鍵字改成整詞比對
> 一句話：風險關鍵字只在整詞出現時才算命中（三個字元以上的英文詞允許 s／es 複數形），規則只寫在 `src/domain/keyword_match.py`。

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
  - 不分大小寫；關鍵字前後緊鄰 ASCII 字母或數字就不算命中。
  - 長度 ≥ `PLURAL_MIN_LEN`（3）且結尾是英文字母的關鍵字，加 `s`／`es` 也算命中，避免 `tariff` 漏掉 `tariffs`。
  - 只有 ASCII 字母數字算字元，所以中文關鍵字在中文句子裡照樣命中。
- 不做的事：不改門檻、不改權重、不清關鍵字資料、不動權重調升邏輯。

## 3 後果與部署前提
- 部署後，個股新聞與全球事件兩條路徑的觸發都會變少。下游的全球事件過濾器、冷卻、停機閘門不變。
- `it`、`am` 是真的英文字，整詞比對擋不掉它們，所以光靠這一步只能讓新聞觸發大約減半。

## 4 可重跑的證明
```bash
.venv/bin/python -m pytest tests/unit/domain/test_keyword_match.py -q
```
上週觸發的模擬（只用議會紀錄裡的新聞標題，實際比對還含摘要，所以真實觸發會略高）：子字串 33／44 次，整詞 17／44 次。重跑方式：從 `council_minutes` 匯出 10-17～10-23 的 `topic`，從 `risk_keywords` 匯出啟用中的 `keyword, weight, source`，用 `keyword_in_text` 重新算每則標題的總權重，與 0.6 比較。

## 已知殘留
- 垃圾關鍵字（`es`、`it`、`am` 等）仍在資料表裡，權重仍是 1.0。清理是正式 DB 寫入，另案處理。
- 權重依命中次數調升的迴圈沒動。
- 單靠這一步，估計每週仍約 $1.6，還沒降到 $1。要降到預算內，需要 shadow 規則觀察一週後切換，加上關鍵字清理。

## 驗收條件
- AC1：`es` 不命中 `Names`、`close` 不命中 `disclosed`；反驗：把 `keyword_in_text` 改回 `in`，`test_keyword_inside_another_word_does_not_match` 要失敗。
- AC2：`tariff` 命中 `tariffs`、`關稅` 命中中文句子；反驗：拿掉複數規則，`test_plural_of_a_word_of_three_or_more_letters_matches` 要失敗。
- AC3：三個呼叫點都經過 `keyword_in_text`；反驗：`grep -rn "keyword.lower() in" src` 應無結果。
