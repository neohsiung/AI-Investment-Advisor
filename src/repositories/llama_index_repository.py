"""
Custom PGVectorStore for LlamaIndex — bridges existing PAD vector infrastructure.
LlamaIndex 自定義 PGVectorStore — 橋接現有 PAD 向量基礎設施。

Provides a custom VectorStore that wraps the existing AlchemyVectorRepository,
allowing LlamaIndex to index/search through the same pgvector backend used
by PAD's agent memory system.
提供自定義 VectorStore，包裝現有的 AlchemyVectorRepository，
允許 LlamaIndex 通過 PAD 代理記憶系統使用的相同 pgvector 後端進行索引/搜尋。
"""
from __future__ import annotations

import uuid
import json
import logging
from typing import List, Dict, Any, Optional, Set
from datetime import datetime

from llama_index.core.vector_stores import (
    VectorStore,
    VectorStoreQuery,
    VectorStoreQueryResult,
    MetadataInfo,
    MetadataFilter,
    MetadataFilters,
)
from llama_index.core.schema import TextNode, BaseNode, NodeRelationship, RelatedNodeInfo
from llama_index.core.vector_stores.types import (
    FilterOperator,
)

from src.repositories.vector_repository import AlchemyVectorRepository, IVectorRepository
from src.data.database import get_db_engine
from src.utils.logger import setup_logger

logger = setup_logger("LlamaIndexRepository")


class PADVectorStore(VectorStore):
    """
    Custom VectorStore adapter for PAD's existing pgvector infrastructure.
    PAD 現有 pgvector 基礎設施的自定義 VectorStore 適配器。

    Wraps AlchemyVectorRepository so LlamaIndex operations (add, delete, query)
    map to the same memory_embeddings table used by PAD agents.
    包裝 AlchemyVectorRepository，使 LlamaIndex 操作映射到 PAD Agent 使用的同一張 memory_embeddings 表。
    """

    stores_text: bool = True
    flat_metadata: bool = False

    def __init__(
        self,
        repo: Optional[AlchemyVectorRepository] = None,
        user_id: str = "default",
        category: str = "llama_index",
    ):
        super().__init__()
        self._repo = repo or AlchemyVectorRepository(engine=get_db_engine())
        self._user_id = user_id
        self._category = category
        logger.info(f"PADVectorStore initialized | user_id={user_id} | category={category}")

    @property
    def client(self):
        """Return the underlying repository (for LlamaIndex compatibility)."""
        return self._repo

    # ── Add ──────────────────────────────────────────────────────────────

    def add(self, nodes: List[BaseNode]) -> List[str]:
        """
        Add nodes to the vector store.
        將節點加入向量儲存庫。

        Args:
            nodes: List of LlamaIndex nodes with embeddings

        Returns:
            List of node IDs
        """
        ids: List[str] = []
        for node in nodes:
            node_id = node.node_id or str(uuid.uuid4())
            embedding = node.get_embedding()
            if not embedding:
                logger.warning(f"Node {node_id} has no embedding, skipping")
                continue

            metadata = {
                **(node.metadata or {}),
                "category": self._category,
                "llama_index_id": node_id,
                "ref_doc_id": node.ref_doc_id or "",
            }

            self._repo.add_memory(
                user_id=self._user_id,
                category=self._category,
                content=node.get_content(),
                embedding=embedding,
                metadata=metadata,
            )
            ids.append(node_id)

        logger.debug(f"Added {len(ids)} nodes to PADVectorStore")
        return ids

    # ── Delete ───────────────────────────────────────────────────────────

    def delete(self, ref_doc_id: str, **delete_kwargs: Any) -> None:
        """
        Delete nodes by reference document ID.
        根據參考文件 ID 刪除節點。
        """
        from sqlalchemy import text

        with self._repo.engine.begin() as conn:
            conn.execute(
                text(
                    "DELETE FROM memory_embeddings "
                    "WHERE user_id = :uid AND metadata->>'ref_doc_id' = :rid"
                ),
                {"uid": self._user_id, "rid": ref_doc_id},
            )
        logger.info(f"Deleted entries with ref_doc_id={ref_doc_id}")

    # ── Query ────────────────────────────────────────────────────────────

    def query(self, query: VectorStoreQuery, **kwargs: Any) -> VectorStoreQueryResult:
        """
        Query the vector store for similar nodes.
        查詢向量儲存庫以尋找相似節點。

        Args:
            query: VectorStoreQuery with query_embedding, similarity_top_k, filters

        Returns:
            VectorStoreQueryResult with nodes, similarities, and ids
        """
        if query.query_embedding is None:
            logger.warning("Query embedding is None, returning empty results")
            return VectorStoreQueryResult(nodes=[], similarities=[], ids=[])

        # Build metadata filter from query filters
        extra_filter: Optional[Dict[str, str]] = None
        if query.filters:
            extra_filter = self._filters_to_dict(query.filters)

        # Search using the existing repository
        results = self._repo.search_memory(
            user_id=self._user_id,
            embedding=query.query_embedding,
            top_k=query.similarity_top_k or 5,
            threshold=0.6,
        )

        if not results:
            return VectorStoreQueryResult(nodes=[], similarities=[], ids=[])

        nodes: List[TextNode] = []
        similarities: List[float] = []
        ids: List[str] = []

        for r in results:
            node = TextNode(
                text=r.get("content", ""),
                metadata=r.get("metadata", {}),
                id_=r.get("id", str(uuid.uuid4())),
            )
            nodes.append(node)
            similarities.append(r.get("similarity", 0.0))
            ids.append(node.node_id)

        return VectorStoreQueryResult(nodes=nodes, similarities=similarities, ids=ids)

    # ── Metadata Helpers ────────────────────────────────────────────────

    def _filters_to_dict(self, filters: MetadataFilters) -> Dict[str, str]:
        """
        Convert LlamaIndex MetadataFilters to a simple dict for pgvector query.
        將 LlamaIndex MetadataFilters 轉換為 pgvector 查詢的簡單字典。
        """
        result: Dict[str, str] = {}
        for f in filters.filters or []:
            if isinstance(f, MetadataFilter):
                result[f.key] = str(f.value)
            elif isinstance(f, MetadataFilters):
                result.update(self._filters_to_dict(f))
        return result
