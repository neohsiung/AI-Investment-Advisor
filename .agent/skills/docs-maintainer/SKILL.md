---
name: docs-maintainer
description: 維護 docs/ 文件與相對連結檢查的技能包（取代已退役的 wiki-maintainer）。
---

# Docs Maintainer Skill

舊 GitHub wiki 已退役，技術文件放在 repo 的 `docs/`，跟程式一起走 PR。本技能只負責一件事：確認 `docs/` 內的 markdown 相對連結都指到存在的檔案。

## 使用

```bash
# 驗證 docs/ 連結完整性（有壞連結回傳 1）
python .agent/skills/docs-maintainer/scripts/verify_docs_links.py
```

這支會在三處執行：`.github/workflows/ci-cd.yml`、`scripts/pre_push_check.sh`、`scripts/ci_local.sh`。

## 規則

- 連結一律用相對路徑，例如 `[系統全景圖](../01_System_Architecture/系統全景圖-System-Landscape.md)`；不用 wiki 的扁平連結，也就是只寫頁名的那種。
- 文件和程式放同一個 PR，commit 用 `docs(scope): 繁中摘要`，不再有第二個 repo。
- 分工與哪些頁有搬過來，見 `docs/README.md`。

## 檢查清單

- [ ] `verify_docs_links.py` 回報 0 個壞連結
- [ ] 文件沒有個人信箱、家目錄路徑或真實帳戶金額
- [ ] 行為描述附可重跑的驗證指令
