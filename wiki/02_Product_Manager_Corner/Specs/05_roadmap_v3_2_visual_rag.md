# Roadmap v3.2 Spec: Infinite Research Analyst (Visual RAG)

> **[⬅️ Back to Roadmap](../產品藍圖-Roadmap.md)**


**Status**: In Progress (Mar 2026 Target)
**Core Value**: Deep Insight @ Zero Cost
**Tech Stack**: ColPali, Qdrant, Local VLM

---

## [Chinese] 產品規格與技術框架

### 1. 產品規格 (Product Specification)

#### 1.1 用戶痛點 (The User Problem)
零售投資人沒有時間或金錢去閱讀數百份長達 100 頁的年度報告 (10-K)。他們依賴往往膚淺或有偏見的新聞摘要。他們害怕錯過隱藏在腳註和圖表中的風險或機會。

#### 1.2 解決方案：無限研究員 (The Solution: "Infinite Research Analyst")
一個 24/7 全天候運作的自主代理 (Autonomous Agent)，它能閱讀**所有內容**——不僅是文字，還包括圖表、表格和複雜的排版——就像一位人類資深分析師一樣。

#### 1.3 關鍵功能 (Key Features)
*   **財報誠實度掃描 (Chart-Truth Scanner)**: 瞬間識別公司樂觀文字與實際財務圖表之間的差異。
    *   *User Story*: 「顯示過去 5 年中，每一張趨勢線與 CEO 宣稱的『強勁增長』相矛盾的營收圖表。」
*   **視覺腳註獵人 (Visual Footnote Hunter)**: 放大檢視表格中通常隱藏債務或資產負債表外負債的細則。
*   **供應鏈視覺化 (Supply Chain Visualizer)**: 自動將文字描述中的供應商和客戶映射成視覺化圖表。

### 2. 技術框架：視覺文件理解 (VDU)

#### 2.1 傳統 RAG 為何失敗 (Why Traditional RAG Fails)
標準 RAG (OCR -> 文字 -> 嵌入) 破壞了財務表格的空間上下文。它將資產負債表變成了一堆混亂的數字湯。

#### 2.2 解決方案：ColPali (Visual Embeddings)
我們使用 **ColPali** (視覺語言模型) 將 PDF 頁面視為 **圖片** 處理。

*   **架構流程**:
    1.  **攝取 (Ingestion)**: 將 PDF 頁面轉換為高解析度圖片。
    2.  **區塊嵌入 (Patch Embedding)**: ColPali 將頁面分割為視覺區塊，並建立捕捉 **版面佈局** 與 **內容** 的多向量嵌入。
    3.  **儲存 (Storage)**: 將這些視覺向量索引至 **Qdrant** (向量資料庫)。
    4.  **檢索 (Retrieval)**: 當用戶問「債務是多少？」時，Qdrant 檢索的是債務表格的 **圖片區塊**，而不僅僅是文字。
    5.  **生成 (Generation)**: 本地 VLM (如 Llava 或 GPT-4o-mini) 觀察檢索到的圖片區塊，以 100% 的數據保真度回答問題。

#### 2.3 成本優勢 (Cost Advantage)
*   **零 OCR 成本**: 不需要昂貴的 OCR API。
*   **減少 Token**: 我們只將相關的 **視覺區塊** 提供給 LLM，而不是整份文件的文字。

---

## [English] Product Spec & Technical Framework

### 1. Product Specification

#### 1.1 The User Problem
Retail investors cannot afford the time or money to read hundreds of 100-page Annual Reports (10-K). They rely on news summaries which are often shallow or biased. They fear "missing out" on hidden risks or opportunities buried in the footnotes and charts.

#### 1.2 The Solution: "Infinite Research Analyst"
A 24/7 autonomous agent that reads *everything*—not just text, but charts, tables, and complex layouts—just like a human senior analyst.

#### 1.3 Key Features
*   **Chart-Truth Scanner**: Instantly identifies discrepancies between a company's optimistic text and its actual financial charts.
    *   *User Story*: "Show me every revenue chart from the last 5 years where the trend line contradicts the CEO's 'strong growth' claim."
*   **Visual Footnote Hunter**: Zooms in on the fine print in tables that often hides debt or off-balance-sheet liabilities.
*   **Supply Chain Visualizer**: Automatically maps suppliers and customers from textual descriptions into a visual graph.

### 2. Technical Framework: Visual Document Understanding (VDU)

#### 2.1 Why Traditional RAG Fails
Standard RAG (OCR -> Text -> Embedding) destroys the spatial context of financial tables. It turns a balance sheet into a soup of numbers.

#### 2.2 The Solution: ColPali (Visual Embeddings)
We use **ColPali** (Vision Language Model) to treat PDF pages as *images*.

*   **Architecture Flow**:
    1.  **Ingestion**: Convert PDF pages to high-res images.
    2.  **Patch Embedding**: ColPali divides the page into visual patches and creates multi-vector embeddings that capture *layout* and *content*.
    3.  **Storage**: Index these visual vectors in **Qdrant** (Vector DB).
    4.  **Retrieval**: When User asks "What is the debt?", Qdrant retrieves the *image patch* of the debt table, not just text.
    5.  **Generation**: A Local VLM (e.g., Llava or GPT-4o-mini) looks at the retrieved image patch to answer the question with 100% data fidelity.

#### 2.3 Cost Advantage
*   **Zero OCR Cost**: No need for expensive OCR APIs.
*   **Reduced Tokens**: We only feed relevant *visual patches* to the LLM, not the whole document text.

## 3. Implementation Steps
1.  **Data Pipeline**: Build a PDF-to-Image converter pipeline using `pdf2image`.
2.  **Vector Store**: Deploy `Qdrant` locally or on cloud.
3.  **Model Integration**: Integrate `ColPali` for embedding generation.
4.  **Frontend**: Build a "Visual Citation" UI where the chatbot highlights the exact region in the chart/table it used for the answer.
