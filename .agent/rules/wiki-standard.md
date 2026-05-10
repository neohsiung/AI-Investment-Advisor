# Wiki Standard

## 目錄結構

Wiki 根目錄: `wiki/`

```
wiki/
├── Home.md                    # 首頁 — 強制存在
├── _Sidebar.md                # 側邊欄 — 強制存在
│
├── 00_Product_Strategy/       # 產品策略、規格書、路線圖
│   ├── Optimization-Roadmap.md
│   └── Specs/                 # 細部規格
│
├── 01_System_Architecture/    # 系統架構、模組設計
│   ├── System-Landscape.md
│   ├── Module-Map.md
│   └── Task-Board.md          # 待辦事項看板
│
├── 02_Frontend_UX/            # 前端
│
├── 03_Backend_Intelligence/   # 後端智能層（LLM、Agent、路由）
│
├── 04_Data_Storage/           # 資料儲存層（DB、Redis）
│
├── 05_Quality_Assurance/      # 測試、規範、設計模式
│   ├── Patterns/              # 設計模式
│   └── Tools-and-Integration/ # 工具與整合
│
├── 06_SRE_Observability/      # 維運、監控、部署
│
└── Archive/                   # 已淘汰／歷史文件
    ├── Legacy-Root/           # 原本在根目錄的舊檔
    └── Project-History/       # 專案歷史記錄
```

## 檔案命名規則

- 只允許 **英文** + **數字** + **連字號** (-) — 禁止中文字元
- 格式：`Pascal-Case-Description.md`
- 禁止數字前綴（如 `P1.1-`、`01-`）
- 範例：❌ `架構總綱-Architecture-Blueprint.md` → ✅ `Architecture-Blueprint.md`

## 分類歸檔規則

| 編號 | 分類 | 內容 |
|------|------|------|
| 00 | Product Strategy | 路線圖、產品規格、商業策略 |
| 01 | System Architecture | 系統全景、模組地圖、架構決策、任務看板 |
| 02 | Frontend UX | 前端框架、UI 規範、UX 指南 |
| 03 | Backend Intelligence | Agent、LLM 路由、決策引擎、NLP |
| 04 | Data Storage | ORM、Repository、Redis、資料管道 |
| 05 | Quality Assurance | 測試規範、設計模式、開發標準、安全 |
| 06 | SRE Observability | 部署、監控、設定、維運手冊 |
| Archive | 已淘汰 | 舊版文件保留但不納入 Sidebar |

## 檢核機制

執行 `wiki-validate` script 檢查：

```bash
make wiki-check
# 或直接執行：
# python scripts/wiki_validator.py
```

檢核項目：

1. ✅ `Home.md` 存在
2. ✅ `_Sidebar.md` 存在
3. ✅ 所有檔案名稱無中文字元
4. ✅ 所有檔案名稱無數字前綴
5. ✅ 無重複目錄（如 `02_Tools_and_Integration` vs `02_常用工具與整合-Tools_and_Integration`）
6. ✅ 所有 .md 檔案位於六個主要分類或 Archive 下（不在 root 層散落）
7. ✅ `_Sidebar.md` 包含所有非 Archive 文件的連結