import logging
import json
import sqlite3
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

# Try importing sqlite-vec
try:
    import sqlite_vec
    HAS_SQLITE_VEC = True
except ImportError:
    HAS_SQLITE_VEC = False
    logger.warning("HybridMemory: sqlite-vec not found. Vector capabilities disabled.")

class HybridMemory:
    """
    OpenClaw Layer 4: Memory Subsystem.
    Combines Vector Search (Semantic) and FTS5 (Keyword) for high-recall memory.
    Fusion Logic:
      Score = (VectorScore * vector_weight) + (BM25Score * keyword_weight)
    """

    def __init__(self, db_path: str = "data/memory.db", vector_dim: int = 1536):
        self.db_path = db_path
        self.vector_dim = vector_dim
        self.vector_weight = 0.7
        self.keyword_weight = 0.3
        
        self._init_db()

    def _init_db(self):
        """Initializes SQLite with FTS5 and Vector tables."""
        conn = sqlite3.connect(self.db_path)
        
        # Load extensions if needed
        if HAS_SQLITE_VEC:
            conn.enable_load_extension(True)
            sqlite_vec.load(conn)
        
        cursor = conn.cursor()
        
        # 1. Main Memory Table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                category TEXT,
                content TEXT,
                metadata TEXT,
                created_at TEXT
            )
        ''')
        
        # 2. FTS5 Virtual Table (Keyword Index)
        cursor.execute('''
            CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
                content, 
                content='memories', 
                content_rowid='rowid'
            )
        ''')
        
        # 3. Vector Virtual Table (Semantic Index)
        if HAS_SQLITE_VEC:
            # Note: sqlite-vec syntax might vary slightly by version
            cursor.execute(f'''
                CREATE VIRTUAL TABLE IF NOT EXISTS memories_vec USING vec0(
                    embedding float[{self.vector_dim}]
                )
            ''')
            
        conn.commit()
        conn.close()

    def add_memory(self, memory_id: str, user_id: str, content: str, embedding: List[float], category: str = "general", metadata: Dict = None):
        """
        Inserts a memory into SQL, FTS, and Vector tables.
        Atomic transaction.
        """
        conn = sqlite3.connect(self.db_path)
        if HAS_SQLITE_VEC:
            conn.enable_load_extension(True)
            sqlite_vec.load(conn)
            
        try:
            cursor = conn.cursor()
            meta_json = json.dumps(metadata or {})
            created_at = datetime.utcnow().isoformat()
            
            # 1. Insert Core Data
            cursor.execute(
                "INSERT INTO memories (id, user_id, category, content, metadata, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (memory_id, user_id, category, content, meta_json, created_at)
            )
            row_id = cursor.lastrowid
            
            # 2. Update FTS Index (Triggers manually or via table definition)
            cursor.execute(
                "INSERT INTO memories_fts (rowid, content) VALUES (?, ?)",
                (row_id, content)
            )
            
            # 3. Insert Vector
            if HAS_SQLITE_VEC and embedding:
                # Ensure float32 array or bytes
                cursor.execute(
                    "INSERT INTO memories_vec (rowid, embedding) VALUES (?, ?)",
                    (row_id, embedding) # sqlite-vec handles list of floats
                )
            
            conn.commit()
            logger.info(f"HybridMemory: Added memory {memory_id}")
            
        except Exception as e:
            conn.rollback()
            logger.error(f"HybridMemory: Add failed: {e}")
            raise
        finally:
            conn.close()

    def search(self, query_text: str, query_vector: List[float], limit: int = 5) -> List[Dict]:
        """
        Performs Hybrid Search (Vector + Keyword Fusion).
        """
        conn = sqlite3.connect(self.db_path)
        if HAS_SQLITE_VEC:
            conn.enable_load_extension(True)
            sqlite_vec.load(conn)
            
        try:
            results_map = {} # rowid -> {score, data...}

            # --- A. Vector Search ---
            if HAS_SQLITE_VEC and query_vector:
                # vec0 query: select rowid, distance from memories_vec where embedding match ? k = ?
                # distance is typically L2 or Cosine depending on build. Assume Cosine similarity or convert distance.
                # sqlite-vec usually returns distance. Low distance = High similarity.
                # Let's assume cosine distance (0..2). Sim = 1 - (dist/2) approx.
                cursor = conn.execute(
                    f"SELECT rowid, distance FROM memories_vec WHERE embedding MATCH ? AND k = ?",
                    (query_vector, limit * 2)
                )
                for rowid, distance in cursor.fetchall():
                    # Normalizing distance to 0..1 score.
                    # This depends on metric. If cosine distance: 0 (same) to 2 (opp).
                    sim_score = max(0, 1 - (distance / 2)) 
                    results_map[rowid] = {"vector_score": sim_score, "ft_score": 0}

            # --- B. Keyword Search (BM25) ---
            # FTS5 rank is bm25 score (standard). Higher is better.
            cursor = conn.execute(
                "SELECT rowid, rank FROM memories_fts WHERE memories_fts MATCH ? ORDER BY rank LIMIT ?",
                (query_text, limit * 2)
            )
            for rowid, rank in cursor.fetchall():
                # Rank is negative in FTS5 default? Or positive?
                # Usually significantly lower is better/worse depending on impl.
                # Let's treat rank as 'Score' directly or normalize logic.
                # Common pattern: score = -rank (since bm25 triggers)
                # For simplicity, we assume rank needs normalization or just relative.
                # We'll use a Reciprocal Rank Fusion style if raw scores distinct.
                # Here, let's just create entry.
                ft_score = abs(rank) # Placeholder normalization
                
                if rowid in results_map:
                    results_map[rowid]["ft_score"] = ft_score
                else:
                    results_map[rowid] = {"vector_score": 0, "ft_score": ft_score}

            # --- C. Weighted Fusion ---
            final_results = []
            
            # Fetch actual content for matched rowids
            if not results_map:
                return []
                
            matched_ids = ",".join(map(str, results_map.keys()))
            cursor = conn.execute(f"SELECT rowid, id, content, metadata FROM memories WHERE rowid IN ({matched_ids})")
            
            rows = {r[0]: r for r in cursor.fetchall()}
            
            for rowid, scores in results_map.items():
                if rowid not in rows: continue
                
                # Normalize scores (Dummy Logic - In prod use standard scaler)
                v_score = scores["vector_score"]
                t_score = min(scores["ft_score"], 1.0) # Cap at 1.0 for now
                
                # Fusion Formula
                final_score = (v_score * self.vector_weight) + (t_score * self.keyword_weight)
                
                db_row = rows[rowid]
                final_results.append({
                    "id": db_row[1],
                    "content": db_row[2],
                    "metadata": json.loads(db_row[3]),
                    "score": final_score,
                    "debug": scores
                })

            # Sort by fused score
            final_results.sort(key=lambda x: x["score"], reverse=True)
            return final_results[:limit]
            
        finally:
            conn.close()
