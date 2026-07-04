"""
LlamaIndex Tools — MCP tools for financial RAG operations.
LlamaIndex 工具 — 金融 RAG 操作的 MCP 工具。

Registers tools that enable PAD agents (CIO, Fundamental, Sentinel, Research)
to ingest and search financial documents via LlamaIndex + pgvector.
註冊工具，讓 PAD Agent (CIO, Fundamental, Sentinel, Research) 能夠
透過 LlamaIndex + pgvector 載入和搜尋金融文件。
"""
from __future__ import annotations

import os
import json
from typing import List, Dict, Any, Optional, TYPE_CHECKING

from src.utils.logger import setup_logger

if TYPE_CHECKING:
    from src.tools.mcp_server import McpServer, McpTool

logger = setup_logger("LlamaIndexTools")


class LlamaIndexTools:
    """
    Registers LlamaIndex-based RAG tools into the PAD MCP server.
    將基於 LlamaIndex 的 RAG 工具註冊到 PAD MCP 伺服器。

    Provides agents with:
    - Semantic search across ingested financial reports and news
    - PDF ingestion for new reports
    - Index statistics and management
    """

    def __init__(self, user_id: str = "default"):
        self._user_id = user_id
        self._service = None  # lazy-init to avoid heavy import at module level
        logger.info(f"LlamaIndexTools initialized | user_id={user_id}")

    def _get_service(self):
        """
        Lazy-init the LlamaIndexService.
        延遲初始化 LlamaIndexService。
        """
        if self._service is None:
            from src.services.llama_index_service import LlamaIndexService
            self._service = LlamaIndexService()
        return self._service

    def register(self, mcp_server: "McpServer") -> None:
        """
        Register all LlamaIndex tools into the MCP server.
        將所有 LlamaIndex 工具註冊到 MCP 伺服器。
        """
        from src.tools.mcp_server import McpTool

        tools: List[McpTool] = [
            McpTool(
                name="llama_search_reports",
                description=(
                    "Search ingested financial reports, earnings calls, "
                    "and analysis documents by semantic similarity. "
                    "搜尋已載入的財報、電話會議和分析文件。"
                ),
                func=self.search_reports,
                schema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Natural language search query / 自然語言查詢",
                        },
                        "ticker": {
                            "type": "string",
                            "description": "Filter by stock ticker (optional) / 按股票代碼過濾（可選）",
                        },
                        "top_k": {
                            "type": "integer",
                            "description": "Number of results (default: 5)",
                            "default": 5,
                        },
                    },
                    "required": ["query"],
                },
                category="rag",
            ),
            McpTool(
                name="llama_search_news",
                description=(
                    "Search ingested news articles and RSS feeds by semantic similarity. "
                    "搜尋已載入的新聞文章和 RSS 訂閱。"
                ),
                func=self.search_news,
                schema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Natural language search query / 自然語言查詢",
                        },
                        "ticker": {
                            "type": "string",
                            "description": "Filter by ticker (optional) / 按股票代碼過濾（可選）",
                        },
                        "top_k": {
                            "type": "integer",
                            "description": "Number of results (default: 5)",
                            "default": 5,
                        },
                    },
                    "required": ["query"],
                },
                category="rag",
            ),
            McpTool(
                name="llama_ingest_pdf",
                description=(
                    "Ingest a financial PDF into the vector index for semantic search. "
                    "將金融 PDF 載入向量索引以進行語意搜尋。"
                ),
                func=self._ingest_pdf,
                schema={
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Absolute path to the PDF file / PDF 檔案的絕對路徑",
                        },
                        "ticker": {
                            "type": "string",
                            "description": "Associated stock ticker / 關聯股票代碼",
                        },
                        "doc_type": {
                            "type": "string",
                            "description": "Document type: earnings, 10-K, 10-Q, report (default: report)",
                            "default": "report",
                        },
                    },
                    "required": ["file_path"],
                },
                category="rag",
            ),
            McpTool(
                name="llama_index_stats",
                description=(
                    "Get statistics about the vector index (document count, etc.). "
                    "取得向量索引的統計資料（文件數等）。"
                ),
                func=self._index_stats,
                schema={
                    "type": "object",
                    "properties": {},
                },
                category="rag",
            ),
        ]

        for tool in tools:
            mcp_server.register_tool(tool)
            logger.info(f"Registered tool: {tool.name}")

    # ── Search Handlers ──────────────────────────────────────────────────

    async def search_reports(
        self,
        query: str,
        ticker: str = "",
        top_k: int = 5,
    ) -> str:
        """
        Search financial reports index.
        搜尋財報索引。
        """
        svc = self._get_service()

        filters = {}
        if ticker:
            filters["ticker"] = ticker

        try:
            results = await svc.search(
                query=query,
                table_name="llama_index_vectors",
                top_k=top_k,
                metadata_filters=filters if filters else None,
            )

            if not results:
                return json.dumps({
                    "status": "ok",
                    "count": 0,
                    "results": [],
                    "note": "No matching documents found. Use llama_ingest_pdf to add documents first.",
                }, ensure_ascii=False, indent=2)

            return json.dumps({
                "status": "ok",
                "count": len(results),
                "results": [
                    {
                        "content": r["content"],
                        "score": round(r["score"], 4),
                        "source": r["metadata"].get("source", "unknown"),
                        "ticker": r["metadata"].get("ticker", ""),
                        "doc_type": r["metadata"].get("doc_type", ""),
                    }
                    for r in results
                ],
            }, ensure_ascii=False, indent=2)

        except Exception as e:
            logger.error(f"search_reports failed: {e}")
            return json.dumps({
                "status": "error",
                "error": str(e),
            })

    async def search_news(
        self,
        query: str,
        ticker: str = "",
        top_k: int = 5,
    ) -> str:
        """
        Search news index.
        搜尋新聞索引。
        """
        svc = self._get_service()

        filters = {}
        if ticker:
            filters["ticker"] = ticker

        try:
            results = await svc.search(
                query=query,
                table_name="llama_index_news",
                top_k=top_k,
                metadata_filters=filters if filters else None,
            )

            if not results:
                return json.dumps({
                    "status": "ok",
                    "count": 0,
                    "results": [],
                    "note": "No matching news found. Use llama_ingest_pdf or RSS pipeline to add data first.",
                }, ensure_ascii=False, indent=2)

            return json.dumps({
                "status": "ok",
                "count": len(results),
                "results": [
                    {
                        "content": r["content"],
                        "score": round(r["score"], 4),
                        "source": r["metadata"].get("source", "unknown"),
                        "ticker": r["metadata"].get("ticker", ""),
                        "ingested_at": r["metadata"].get("ingested_at", ""),
                    }
                    for r in results
                ],
            }, ensure_ascii=False, indent=2)

        except Exception as e:
            logger.error(f"search_news failed: {e}")
            return json.dumps({
                "status": "error",
                "error": str(e),
            })

    async def _ingest_pdf(
        self,
        file_path: str,
        ticker: str = "",
        doc_type: str = "report",
    ) -> str:
        """
        Ingest a PDF into the index.
        將 PDF 載入索引。
        """
        svc = self._get_service()

        try:
            result = await svc.ingest_pdf(
                file_path=file_path,
                ticker=ticker,
                doc_type=doc_type,
            )
            return json.dumps(result, ensure_ascii=False, indent=2)
        except FileNotFoundError as e:
            return json.dumps({"status": "error", "error": str(e)})
        except Exception as e:
            logger.error(f"PDF ingestion failed: {e}")
            return json.dumps({"status": "error", "error": f"Ingestion failed: {e}"})

    async def _index_stats(self) -> str:
        """
        Get vector index statistics.
        取得向量索引統計資料。
        """
        svc = self._get_service()

        try:
            stats = await svc.get_index_stats()
            return json.dumps(stats, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Index stats failed: {e}")
            return json.dumps({"status": "error", "error": str(e)})
