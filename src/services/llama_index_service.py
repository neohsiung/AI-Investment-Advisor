"""
LlamaIndex Service — RAG Data Hub for Financial Knowledge.
LlamaIndex 服務 — 金融知識的 RAG 資料中樞。

Provides document ingestion (PDF, RSS), vector indexing via Ollama embeddings,
and semantic search backed by PostgreSQL/pgvector.
提供文件載入 (PDF, RSS)、透過 Ollama 嵌入進行向量索引，
以及由 PostgreSQL/pgvector 支援的語意搜尋。
"""
from __future__ import annotations

import os
import uuid
import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from llama_index.core import (
    VectorStoreIndex,
    StorageContext,
    Document,
    Settings,
)
from llama_index.core.node_parser import SimpleNodeParser
from llama_index.core.ingestion import IngestionPipeline
from llama_index.core.schema import MetadataMode
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.llms.ollama import Ollama
from llama_index.vector_stores.postgres import PGVectorStore
from llama_index.readers.file import PDFReader
from src.utils.logger import setup_logger

logger = setup_logger("LlamaIndexService")


class RssNewsReader:
    """
    Custom RSS news reader that parses RSS feeds using feedparser and extracts text using newspaper3k.
    Does not require llama-index-readers-web (which depends on GPL-licensed html2text).
    """
    def __init__(self, **reader_kwargs: Any):
        self.reader_kwargs = reader_kwargs

    def load_data(self, urls: str | List[str]) -> List[Document]:
        import feedparser
        from newspaper import Article

        if isinstance(urls, str):
            urls = [urls]

        documents = []
        for url in urls:
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries:
                    link = entry.get("link")
                    if not link:
                        continue
                    try:
                        article = Article(link, **self.reader_kwargs)
                        article.download()
                        article.parse()
                        
                        metadata = {
                            "title": getattr(article, "title", ""),
                            "link": link,
                            "authors": getattr(article, "authors", []),
                            "language": getattr(article, "meta_lang", ""),
                            "description": getattr(article, "meta_description", ""),
                            "publish_date": getattr(article, "publish_date", ""),
                            "feed": url,
                        }
                        
                        documents.append(
                            Document(text=article.text, metadata=metadata)
                        )
                    except Exception as e:
                        logger.error(f"Error parsing article {link}: {e}")
                        continue
            except Exception as e:
                logger.error(f"Error parsing feed {url}: {e}")
                continue

        return documents

# Default embedding model configuration
DEFAULT_EMBED_MODEL = "nomic-embed-text"
DEFAULT_OLLAMA_BASE_URL = os.environ.get(
    "OLLAMA_BASE_URL", "http://host.docker.internal:11434"
)
EMBED_DIM = 768  # nomic-embed-text dimension


class LlamaIndexService:
    """
    Central service for financial RAG operations via LlamaIndex.
    LlamaIndex 金融 RAG 操作的核心服務。

    Handles document ingestion, vector indexing, and semantic search
    across financial reports, earnings calls, news, and market analysis.
    處理財報、電話會議、新聞和市場分析的文件載入、向量索引和語意搜尋。
    """

    def __init__(
        self,
        db_connection_string: Optional[str] = None,
        embed_model_name: str = DEFAULT_EMBED_MODEL,
        ollama_base_url: str = DEFAULT_OLLAMA_BASE_URL,
    ):
        self._embed_model = OllamaEmbedding(
            model_name=embed_model_name,
            base_url=ollama_base_url,
            embed_batch_size=1,
        )
        self._llm = Ollama(
            model="gemma3:4b",
            base_url=ollama_base_url,
            request_timeout=60.0,
        )
        self._connection_string = db_connection_string or self._default_db_url()
        self._vector_store: Optional[PGVectorStore] = None
        self._index_cache: Dict[str, VectorStoreIndex] = {}
        self._pdf_reader = PDFReader()
        self._rss_reader = RssNewsReader()
        self._node_parser = SimpleNodeParser.from_defaults(chunk_size=1024, chunk_overlap=200)

        # Set global defaults for LlamaIndex
        Settings.embed_model = self._embed_model
        Settings.llm = self._llm
        Settings.chunk_size = 1024
        Settings.chunk_overlap = 200

        logger.info(
            f"LlamaIndexService initialized | embed_model={embed_model_name} "
            f"| ollama={ollama_base_url} | pgvector={self._connection_string.split('@')[-1] if '@' in self._connection_string else 'configured'}"
        )

    @staticmethod
    def _default_db_url() -> str:
        """
        Build default PostgreSQL connection string from environment variables.
        從環境變數建立預設 PostgreSQL 連線字串。
        """
        host = os.environ.get("PGHOST", "postgres")
        port = os.environ.get("PGPORT", "5432")
        db = os.environ.get("PGDATABASE", "advisor_prod")
        user = os.environ.get("DB_USER", "postgres")
        pw = os.environ.get("DB_PASS", "postgres")
        return f"postgresql+psycopg2://{user}:{pw}@{host}:{port}/{db}"

    def _ensure_vector_store(self, table_name: str = "llama_index_vectors") -> PGVectorStore:
        """
        Lazy-init a PGVectorStore for the given table.
        為指定資料表延遲初始化 PGVectorStore。
        """
        cache_key = table_name
        if cache_key not in self._index_cache or self._vector_store is None:
            self._vector_store = PGVectorStore.from_params(
                database=self._connection_string.split("/")[-1],
                host=self._connection_string.split("@")[-1].split(":")[0],
                port=int(self._connection_string.split(":")[-1].split("/")[0]),
                user=self._connection_string.split("://")[1].split(":")[0],
                password=self._connection_string.split(":")[2].split("@")[0],
                table_name=table_name,
                embed_dim=EMBED_DIM,
                use_jsonb=True,
            )
            logger.info(f"PGVectorStore initialized | table={table_name}")
        return self._vector_store

    # ── Document Ingestion ──────────────────────────────────────────────

    async def ingest_pdf(
        self,
        file_path: str,
        ticker: str = "",
        doc_type: str = "report",
        category: str = "financial_report",
    ) -> Dict[str, Any]:
        """
        Ingest a financial PDF document into the vector index.
        將金融 PDF 文件載入向量索引。

        Args:
            file_path: Absolute path to the PDF file / PDF 檔案的絕對路徑
            ticker: Associated stock ticker / 關聯的股票代碼
            doc_type: Document type (earnings, 10-K, 10-Q, etc.)
            category: Content category for metadata filtering

        Returns:
            Dict with ingested document count and metadata
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"PDF not found: {file_path}")

        try:
            documents = self._pdf_reader.load_data(file_path)
            logger.info(f"Loaded {len(documents)} documents from PDF: {file_path}")
        except Exception as e:
            logger.error(f"Failed to load PDF {file_path}: {e}")
            raise

        # Add metadata to each document
        for doc in documents:
            doc.metadata.update({
                "ticker": ticker,
                "doc_type": doc_type,
                "category": category,
                "source": file_path,
                "ingested_at": datetime.utcnow().isoformat(),
            })

        nodes = self._node_parser.get_nodes_from_documents(documents)
        logger.info(f"Split into {len(nodes)} nodes from {file_path}")

        vector_store = self._ensure_vector_store()
        storage_context = StorageContext.from_defaults(vector_store=vector_store)
        index = VectorStoreIndex(
            nodes=nodes,
            storage_context=storage_context,
            embed_model=self._embed_model,
        )

        return {
            "status": "ok",
            "documents": len(documents),
            "nodes": len(nodes),
            "ticker": ticker,
            "doc_type": doc_type,
            "file": file_path,
        }

    async def ingest_rss(
        self,
        rss_urls: List[str],
        ticker: str = "",
        category: str = "news",
    ) -> Dict[str, Any]:
        """
        Ingest RSS/Atom feeds into the vector index.
        將 RSS/Atom 訂閱載入向量索引。

        Args:
            rss_urls: List of RSS feed URLs
            ticker: Associated stock ticker
            category: Content category

        Returns:
            Dict with ingestion results
        """
        all_documents = []
        for url in rss_urls:
            try:
                docs = self._rss_reader.load_data(url)
                for doc in docs:
                    doc.metadata.update({
                        "ticker": ticker,
                        "category": category,
                        "source": url,
                        "ingested_at": datetime.utcnow().isoformat(),
                    })
                all_documents.extend(docs)
                logger.info(f"Loaded {len(docs)} articles from RSS: {url}")
            except Exception as e:
                logger.warning(f"Failed to load RSS {url}: {e}")

        if not all_documents:
            logger.warning("No documents loaded from any RSS feed")
            return {"status": "error", "documents": 0, "rss_urls": rss_urls}

        nodes = self._node_parser.get_nodes_from_documents(all_documents)
        vector_store = self._ensure_vector_store(table_name="llama_index_news")
        storage_context = StorageContext.from_defaults(vector_store=vector_store)
        index = VectorStoreIndex(
            nodes=nodes,
            storage_context=storage_context,
            embed_model=self._embed_model,
        )

        return {
            "status": "ok",
            "documents": len(all_documents),
            "nodes": len(nodes),
            "ticker": ticker,
            "category": category,
            "rss_urls": rss_urls,
        }

    # ── Semantic Search ──────────────────────────────────────────────────

    async def search(
        self,
        query: str,
        table_name: str = "llama_index_vectors",
        top_k: int = 5,
        metadata_filters: Optional[Dict[str, str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Semantic search across ingested financial documents.
        對已載入的金融文件進行語意搜尋。

        Args:
            query: Natural language query / 自然語言查詢
            table_name: Target vector table / 目標向量表
            top_k: Number of results / 回傳數量
            metadata_filters: Optional filter dict (e.g., {"ticker": "NVDA"})

        Returns:
            List of search results with content, metadata, and similarity scores
        """
        vector_store = self._ensure_vector_store(table_name=table_name)
        storage_context = StorageContext.from_defaults(vector_store=vector_store)
        index = VectorStoreIndex(
            nodes=[],
            storage_context=storage_context,
            embed_model=self._embed_model,
        )

        query_engine = index.as_query_engine(
            similarity_top_k=top_k,
            vector_store_kwargs={
                "ivfflat_probes": 10,
            },
        )

        response = query_engine.query(query)

        results = []
        if hasattr(response, "source_nodes") and response.source_nodes:
            for node in response.source_nodes:
                results.append({
                    "content": node.node.get_content(metadata_mode=MetadataMode.NONE),
                    "metadata": node.node.metadata,
                    "score": float(node.score) if node.score else 0.0,
                })

        return results

    async def search_by_ticker(
        self,
        ticker: str,
        query: str,
        top_k: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        Convenience method: search within a specific ticker's documents.
        便捷方法：在特定股票的文檔中搜尋。
        """
        return await self.search(
            query=query,
            metadata_filters={"ticker": ticker},
            top_k=top_k,
        )

    # ── Index Management ─────────────────────────────────────────────────

    async def get_index_stats(self, table_name: str = "llama_index_vectors") -> Dict[str, Any]:
        """
        Get statistics about the vector index.
        取得向量索引的統計資料。
        """
        from sqlalchemy import create_engine, text
        import re

        # Validate table name to prevent SQL injection
        ALLOWED_TABLES = {"llama_index_vectors", "llama_index_news"}
        if table_name not in ALLOWED_TABLES:
            raise ValueError(f"Invalid table name: {table_name}")

        engine = create_engine(self._connection_string)
        try:
            with engine.connect() as conn:
                row = conn.execute(
                    text(f"SELECT COUNT(*) as count FROM {table_name}")  # nosec B608
                ).fetchone()
                return {
                    "table": table_name,
                    "document_count": row[0] if row else 0,
                    "embed_dim": EMBED_DIM,
                    "embed_model": DEFAULT_EMBED_MODEL,
                }
        except Exception as e:
            logger.warning(f"Failed to get index stats: {e}")
            return {"table": table_name, "error": str(e)}

    async def delete_old_entries(
        self,
        days: int = 90,
        table_name: str = "llama_index_vectors",
    ) -> int:
        """
        Delete entries older than N days (data retention policy).
        刪除 N 天前的條目（資料保留政策）。
        """
        from sqlalchemy import create_engine, text
        import re

        # Validate table name to prevent SQL injection
        ALLOWED_TABLES = {"llama_index_vectors", "llama_index_news"}
        if table_name not in ALLOWED_TABLES:
            raise ValueError(f"Invalid table name: {table_name}")

        engine = create_engine(self._connection_string)
        with engine.begin() as conn:
            result = conn.execute(
                text(
                    f"DELETE FROM {table_name} "  # nosec B608
                    "WHERE (data->>'ingested_at')::timestamp < NOW() - (CAST(:days AS TEXT) || ' days')::INTERVAL"
                ),
                {"days": days},
            )
            count = result.rowcount
            logger.info(f"Deleted {count} old entries from {table_name}")
            return count
