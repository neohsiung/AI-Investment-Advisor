# docs/ 說明

> 舊 GitHub wiki 已退役，不再更新。有用的頁面搬到這裡，跟程式一起走 PR。

## docs/ 的分工

| 位置 | 放什麼 |
| :--- | :--- |
| `docs/design/` | 設計決策紀錄 `DD-*.md`，改門檻、規則、契約時要附 |
| `docs/00_` 到 `docs/06_` | 從舊 wiki 搬來的技術文件，分類資料夾沿用原名 |
| `docs/Home.md` | 舊 wiki 首頁：版本紀錄與架構總覽 |
| 根目錄 `README.md` | 對外門面，只放亮點與入口 |

新文件的寫法見 `.agent/rules/documentation-standards.md` 與 `.agent/rules/wiki-standard.md`。內部連結一律用相對路徑，檢查指令：

```bash
python .agent/skills/docs-maintainer/scripts/verify_docs_links.py
```

## 搬過來的頁面

- 入口：`Home.md`
- 維運：`06_SRE_Observability/` 的單機自架手冊、冷備份與可觀測性
- 產品：`00_Product_Strategy/` 的單機轉型路線圖、產品需求規格總綱
- 架構：`01_System_Architecture/` 的系統全景圖
- 品質：`05_Quality_Assurance/` 的靜默失敗防治、端到端行為驅動測試規格、使命與不變量
- 後端：`03_Backend_Intelligence/` 的代理人戰略協定
- 引擎：根目錄 README 引用的四頁，分別是統一投組自適應智慧聚合、貝氏體制轉移、極值理論尾部風險、策略自動演化
- 前端：`02_Frontend_UX/` 的自適應戰情室雷達儀表板

搬移時只清掉個人信箱、家目錄路徑，並把指向沒搬頁面的連結改成純文字，內文沒有改寫。

## 沒搬的頁面

| 分類 | 理由 |
| :--- | :--- |
| `Archive/` | 歷史報告，含個人路徑與帳號，不搬 |
| `03_Backend_Intelligence/` 其餘引擎頁 | 每頁對應單一服務，多數沒有被程式或規範引用；要用時再按需求搬 |
| `04_Data_Storage/`、`01_System_Architecture/` 其餘頁 | 同上；其中交易服務頁含真實帳戶金額與實際設定值，搬之前要先改寫 |
| `05_Quality_Assurance/` 其餘頁 | 技術債清單等容易過期的頁；待辦改放 GitHub Issues |
| `06_SRE_Observability/` 其餘頁 | 腳本操作手冊含個人信箱，需先清理再搬 |
| `_Sidebar.md`、舊 wiki 的檢查腳本 | wiki 專用，沒有對應用途 |

沒搬的頁面仍在舊 wiki 的 git 歷史裡。需要時，從該頁複製到對應的分類資料夾，清掉個資、把連結改成相對路徑，跑一次上面的連結檢查。
