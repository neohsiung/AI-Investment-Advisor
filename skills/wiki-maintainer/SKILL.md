---
name: wiki-maintainer
description: 專指用於 Wiki 文檔維護、連結標準化與架構一致性檢查的技能包。
---

# Wiki Maintainer Skill

本技能提供一組自動化工具與規範說明，用於確保專案 Wiki 始終符合「扁平化連結」標準與「雙語並列」架構。

## 核心功能 (Core Features)

1. **連結標準化 (Standardization)**: 將包含路徑或副檔名的內部連結轉換為 `{basename}` 格式。
2. **完整性驗證 (Integrity Check)**: 遞迴掃描所有 Markdown 文件，識別斷開的內部連結。
3. **模糊匹配 (Fuzzy Mapping)**: 當連結文字與檔名不完全一致時（例如只有英文名），自動匹配至正確的 `{繁中}-{英文}` 檔名。

## 目錄結構 (Directory Structure)

- `SKILL.md`: 技能說明指南。
- `scripts/standardize_wiki_links.py`: 核心標準化邏輯。
- `scripts/verify_wiki_links.py`: 連結健康檢查工具。

## 使用指南 (Usage Guide)

當 Agent 被要求「整理 Wiki」、「修復連結」或「同步文檔」時，應優先調閱本技能腳本。

```bash
# 標準化所有 Wiki 連結
python skills/wiki-maintainer/scripts/standardize_wiki_links.py

# 驗證連結完整性
python skills/wiki-maintainer/scripts/verify_wiki_links.py
```

## 注意事項 (Precautions)

- 腳本執行前，請確保工作區處於 `git clean` 狀態。
- 嚴禁修改外部連結（`http://`）或錨點連結（`#`）。
