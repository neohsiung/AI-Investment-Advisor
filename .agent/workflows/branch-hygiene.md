---
description: 標準化 Remote Branch 清理流程（孤兒 branch、已 merge 未刪、過期 Dependabot PR）
---

# Branch Hygiene Workflow

> 適用時機：安全修復 PR、功能 PR merge 後，或 Dependabot 產生大量分支時。

## Step 1：同步並列出所有 Remote Branch 狀態

```bash
# 同步 remote refs，自動清除已刪除的 tracking branches
git fetch --prune

# 列出所有 remote branches，按 commit 時間排序
git branch -r --sort=-committerdate \
  --format="%(refname:short) | %(committerdate:relative) | %(objectname:short) | %(subject)"
```

## Step 2：找出「已 merge 至 main 但未刪除」的 branches

```bash
git branch -r --merged origin/main | grep -v "origin/main\|HEAD"
# 輸出的每一條都是可以安全刪除的候補
```

## Step 3：分類判斷每個 Branch

對每個候補 branch，依下列規則分類：

| 狀態 | 判斷依據 | 動作 |
|---|---|---|
| ✅ 已 merge | `git branch -r --merged origin/main` 有出現 | 直接刪除 |
| ⚠️ 孤兒（無對應 PR） | GitHub 上找不到任何 open/closed PR | 查看最後 5 commits 後決定 |
| 🤖 Dependabot（已被覆蓋） | 當前安全 PR 的 requirements.txt 已包含相同升級 | 在 PR 留 comment 後關閉 |
| 🔵 Active PR | 有 open PR 且正在進行 | 保留，不動 |

```bash
# 快速查看孤兒 branch 的最後 5 commits
git log origin/<branch-name> --oneline -5
```

## Step 4：執行刪除

```bash
# 刪除已確認的 remote branch
git push origin --delete <branch-name>

# 批次刪除已 merge 的 Dependabot branches（謹慎使用）
git branch -r --merged origin/main \
  | grep "origin/dependabot/" \
  | sed 's|origin/||' \
  | xargs -I{} git push origin --delete {}
```

## Step 5：Dependabot PR 關閉（需人工處理）

若 GitHub PAT 權限不足無法用 API 關閉 PR：

1. 在 PR 頁面留 comment 說明被覆蓋原因：
   ```
   Closing: superseded by PR #XX which includes all security fixes.
   ```
2. 手動點擊 **Close pull request**（不選 merge）

## 完成確認

```bash
# 確認清理後的 remote branch 列表
git branch -r | grep -v "HEAD" | sort
```

預期結果：只剩 `origin/main` + 當前 active 開發 branches。
