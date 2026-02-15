# Coding Standards & Best Practices

## 1. 語言規範 (Language Standards)

### 1.1 繁體中文強制 (Traditional Chinese Mandatory)
- **規則**: 專案中所有出現中文的地方（包含文檔、註解、Commit Message、UI 顯示），**必須**使用繁體中文 (Traditional Chinese)。
- **禁止**: 簡體中文 (Simplified Chinese)。
- **工具**: 使用 `OpenCC` 或編輯器插件進行轉換。

### 1.2 雙語註解規範 (Bilingual Comments)
- **規則**: 程式碼中的註解 (Docstrings, Inline comments) 必須包含 **英文** 與 **繁體中文**。
- **順序**: 英文在上，繁體中文在下。
- **格式**:
  ```python
  def calculate_leverage(self, net_equity: float, loan: float) -> float:
      """
      Calculate the leverage ratio based on net equity and loan.
      計算基於淨權益與貸款的槓桿比率。
      
      Args:
          net_equity (float): The net equity value. (淨權益價值)
          loan (float): The loan value. (貸款價值)
          
      Returns:
          float: The leverage ratio. (槓桿比率)
      """
      # Validate net equity is positive
      # 驗證淨權益為正數
      if net_equity <= 0:
          raise ValueError("Net equity must be positive")
          
      return (net_equity + loan) / net_equity
  ```

## 2. 命名規範 (Naming Conventions)

- **Class**: `PascalCase` (e.g., `AnalyticsService`)
- **Function/Variable**: `snake_case` (e.g., `calculate_net_equity`)
- **Constant**: `UPPER_CASE` (e.g., `MAX_RETRY_COUNT`)
- **Private**: `_leading_underscore` (e.g., `_internal_method`)

## 3. 類型提示 (Type Hinting)

- **規則**: 所有函數定義必須包含 Type Hints。
- **工具**: 使用 `mypy` 進行檢查。
- **範例**:
  ```python
  def fetch_data(ticker: str, limit: int = 100) -> List[Dict[str, Any]]:
      ...
  ```

## 4. 錯誤處理 (Error Handling)

- **規則**: 避免使用裸露的 `try-except`。
- **最佳實踐**: 捕捉特定異常，並提供有意義的錯誤訊息。
- **日誌**: 在 catch block 中記錄異常堆疊 (stack trace)。

## 5. 自動化檢查 (Automation)

此規則應整合至 CI/CD 流程中：
- 檢查是否包含簡體中文
- 檢查 Docstring 是否包含雙語 (啟發式檢查)
