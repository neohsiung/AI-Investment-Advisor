# Archive / 檔案封存區

This directory contains deprecated source files that have been replaced by newer implementations but are kept for reference or historical setup needs.
此目錄包含已被新實作取代的過時原始碼檔案，保留此處是為了參考或滿足歷史設定需求。

## Files / 檔案列表

### `database_deprecated.py`
- **Description (EN)**: Old database connection logic using raw `sqlite3` without SQLAlchemy. Replaced by `src/database.py` which uses SQLAlchemy for better PostgreSQL support and connection pooling.
- **描述 (繁中)**: 舊版的資料庫連線邏輯，直接使用 raw `sqlite3` 而非 SQLAlchemy。已被 `src/database.py` 取代，後者使用 SQLAlchemy 以提供更好的 PostgreSQL 支援與連線池管理。
- **Depreciation Date / 廢棄日期**: 2024-12-06

### `ingestor_deprecated.py`
- **Description (EN)**: Old CSV ingestion logic that was tightly coupled with specific broker formats and lacked robustness. Replaced by `src/ingestor.py` which features a more modular design and improved error handling.
- **描述 (繁中)**: 舊版的 CSV 匯入邏輯，與特定券商格式高度耦合且缺乏穩健性。已被 `src/ingestor.py` 取代，後者具備模組化設計與改良的錯誤處理機制。
- **Depreciation Date / 廢棄日期**: 2024-12-06

## Usage / 使用說明
These files are not loaded by the main application. If you need to restore old functionality:
這些檔案不會被主程式載入。若您需要恢復舊有功能：

1.  Compare the logic with current `src/` files.
    比對此處檔案與目前 `src/` 內檔案的邏輯。
2.  Extract necessary parts manually.
    手動提取所需的部分。
3.  **DO NOT** copy them back to `src/` directly as it may break the current Clean Architecture.
    **請勿** 直接將其複製回 `src/`，以免破壞目前的 Clean Architecture 架構。
