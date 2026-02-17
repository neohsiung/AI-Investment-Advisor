# README 增量強化工作流 (README Enrichment Workflow)

本工作流指導如何以「最佳實踐 (Best Practice)」持續豐富 README 內容，確保其始終具備高吸引力。

## 執行步驟 (Execution Steps)

1. **亮點識別 (Identify Highlights)**
   - 掃描最近的代碼變更或 Wiki 更新內容。
   - 識別具有「外部演示價值」或「架構突破」的特點。

2. **英文內容撰寫 (Draft in English)**
   - 依照 `documentation-standards.md` 的原則，先產出精簡且具吸引力的英文摘要。
   - 增加相關的「徽章 (Badges)」或更新「架構圖 (Mermaid)」。

3. **繁體中文對齊 (Bilingual Alignment)**
   - 將英文內容精確翻譯。
   - 依照 **中文在上、英文在下** 的原則，插入到 `README.md` 的對應章節標籤下方。

4. **視覺與連結校驗 (Visual & Link Audit)**
   - 確認 Markdown 語法無誤，尤其是圖像與連結。
   - 確保 README 中的連結指向的是 Wiki 的最新結構。

5. **執行原子提交 (Atomic Commit)**
   - 依照 `git-commit-format.md` 規範。
   - Commit Message 應反映 README 的增量強化，例如：`docs(readme): enrich agent swarm logic | 強化智能體集群邏輯描述`。

## 吸引力清單 (Attractiveness Checklist)
- [ ] 標題是否具備吸引力？
- [ ] 是否有豐富的技術徽標 (Badges)？
- [ ] 快速開始腳本是否依然有效？
- [ ] 架構圖是否展示了專案的獨特性 (如 7 Agents)？
- [ ] 是否嚴格執行雙語置換工作流？
