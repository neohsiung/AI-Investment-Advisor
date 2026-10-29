# Docs Standard

這份檔名沿用 `wiki-standard.md`，內容已改成 `docs/` 的標準。

舊 GitHub wiki 已退役。技術文件放在 repo 根目錄的 `docs/`，跟程式一起走 PR。哪些頁有搬過來，見 `docs/README.md`。

## 目錄結構

```
docs/
├── README.md                  # docs/ 的分工、搬了哪些頁
├── Home.md                    # 舊 wiki 首頁（版本紀錄與架構總覽）
├── design/                    # 設計決策紀錄 DD-*.md（dev-standard §5）
├── 00_Product_Strategy/       # 產品策略、規格書、路線圖
├── 01_System_Architecture/    # 系統架構、模組設計
├── 02_Frontend_UX/            # 前端
├── 03_Backend_Intelligence/   # 後端智能層（LLM、Agent、路由）
├── 04_Data_Storage/           # 資料儲存層
├── 05_Quality_Assurance/      # 測試、規範、不變量
└── 06_SRE_Observability/      # 維運、部署、自架手冊
```

分類資料夾只在有頁面時才建。

## 檔案命名

- 沿用舊頁的 `{繁體中文}-{English}.md`；新頁照 `.agent/rules/documentation-standards.md` §1.1。
- 檔名不加數字前綴，只有分類資料夾有。

## 連結

- 內部連結一律用相對路徑，指到存在的檔案。
- 檢查指令：`python .agent/skills/docs-maintainer/scripts/verify_docs_links.py`。
- 有壞連結會回傳 1，CI 會跑。

## 內容

- 不放個人信箱、家目錄路徑、真實帳戶金額；範例值要註明「範例」。
- 實際設定值不寫在文件裡，例如 `tradable_capital_usd`。改寫查詢方法，用 API 或 SQL。
- 不寫會漂移的數字。
