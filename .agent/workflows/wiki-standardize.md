---
description: 自動化 Wiki 連結標準化流程 (Standardize Wiki internal links)
---

本工作流旨在自動化 Wiki 內部連結的標準化與驗證，確保所有連結符合 `documentation-standards.md` 的扁平化要求。

## 執行步驟 (Execution Steps)

1. **環境準備 (Setup)**
   - 確保已安裝 `wiki-maintainer` 技能。
   - 確認 `wiki/` 目錄已完全暫存或處於乾淨狀態。

2. **連結識別與標準化 (Identify & Standardize)**
   - 執行標準化腳本：`python skills/wiki-maintainer/scripts/standardize_wiki_links.py`
   - 此腳本將：
     - 去除所有連結中的資料夾路徑。
     - 去除 `.md` 副檔名。
     - 嘗試修復名稱不匹配的連結。

3. **完整性驗證 (Integrity Check)**
   - 執行驗證腳本：`python skills/wiki-maintainer/scripts/verify_wiki_links.py`
   - 檢查是否仍存在斷開的內部連結。

4. **原子提交 (Atomic Commit)**
   - 若驗證通過，根據 `git-commit-format.md` 執行 Wiki Repo 的原子提交。

## 檢查清單 (Checklist)
- [ ] 所有連結是否皆不包含路徑？
- [ ] 所有連結是否皆不包含 `.md`？
- [ ] `verify_wiki_links.py` 是否回報 0 錯誤？
