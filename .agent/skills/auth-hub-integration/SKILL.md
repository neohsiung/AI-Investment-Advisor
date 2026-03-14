# FastAPI Auth Hub 整合技巧 (FastAPI Auth Hub Integration Skill)

## 概述 (Overview)

本 Skill 定義了如何在 Streamlit (Frontend) 與 FastAPI (Backend) 之間建立穩定的認證橋樑。

## 關鍵設計模式 (Key Design Patterns)

### 1. 後端處理回調 (Backend Callback Handling)

**不要**在 Streamlit 中直接處理 OAuth 回調。Streamlit 的多執行緒與異步渲染會導致 Cookie 寫入失敗或遺失。

- **流程**: Streamlit (`<a>` tag) -> `FastAPI /api/auth/login` -> `Google OAuth` -> `FastAPI /api/auth/callback` -> `HTTP 302 Redirect` -> `Streamlit`.
- **優勢**: 利用原生 HTTP `Set-Cookie` 確保 100% 寫入成功。

### 2. 父視窗跳轉技巧 (Parent Window Redirect)

當認證流程完成後，若需要從 iframe (甚至 sandbox 環境) 強制刷新父視窗：

```python
# 在 FastAPI Callback 回傳的 HTML 中注入
html_content = """
<script>
    window.location.href = "/"; // 強制父視窗跳至首頁
</script>
"""
```

### 3. 同步讀取 Cookie (Synchronous Cookie Read)

使用 Streamlit 1.30+ 提供的原生方法，避免組件渲染延遲。

```python
# src/utils/google_auth.py
import streamlit as st

def check_authentification(self):
    return st.context.cookies.get(self.cookie_name)
```

## 常見陷阱 (Pitfalls)

- **iframe 限制**: `st.query_params` 的寫入在某些部署環境會被阻擋，導致認證狀態遺失。
- **Cookie 屬性**: 確保 `samesite="lax"` 且 `httponly=False` (若 Streamlit 需要 JS 讀取) 或 `httponly=True` (安全性更佳，僅限後端與原生 `st.context.cookies` 讀取)。
