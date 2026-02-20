---
name: postgres-raw-sql
description: Enforces Raw SQL usage and parameterized queries for PostgreSQL interactions, especially within Repository classes like TransactionRepository or AlchemyVectorRepository. Use this when writing database queries.
---

# PostgreSQL Raw SQL & Security Guidelines

## When to use this skill
- When creating or modifying Repository classes.
- When querying transactions, position snapshots, or vector embeddings.

## How to use it

### 1. Hybrid Storage Strategy (Rule #9)
- **High-Frequency / Complex Data**: Use **SQLAlchemy Core (Raw SQL)**.
    - Examples: `TransactionRepository`, `AlchemyVectorRepository` (pgvector), `SentinelService` checks.
- **Simple Objects / Admin**: ORM (`Session`) is permissible but optional.
    - Examples: `UserSettings`, `RiskKeyword`.

### 2. Security: Parameterized Queries (Rule #10)
- **NEVER** use f-strings or string concatenation for SQL values.
- **ALWAYS** use bound parameters (e.g., `:value`).

#### ❌ BAD (Vulnerable to SQL Injection)
```python
# DO NOT DO THIS
query = f"SELECT * FROM transactions WHERE symbol = '{symbol}'"
conn.execute(text(query))
```

#### ✅ GOOD (Secure)
```python
stmt = text("SELECT * FROM transactions WHERE symbol = :symbol")
conn.execute(stmt, {"symbol": symbol})
```

### 3. Session Management
- Ensure `close_session()` is called, preferably via a `try...finally` block or context manager usage in the base class.
- Prevent connection pool exhaustion during concurrent Swarm execution.

### 4. Vector Search (pgvector)
- Use standard SQL syntax for vector operations (e.g., `<->` for L2 distance, `<#>` for inner product).
- Ensure the `vector` extension is enabled.

#### Example: Vector Search
```python
def search_similar(self, embedding: List[float], limit: int = 5):
    with self.engine.connect() as conn:
        stmt = text("""
            SELECT id, content, embedding <-> :embedding_val AS distance
            FROM documents
            ORDER BY distance ASC
            LIMIT :limit
        """)
        # pgvector requires passing the embedding as a string representation usually, 
        # but sqlalchemy-pgvector handles lists if configured. 
        # Standard approach for raw text sql:
        return conn.execute(stmt, {
            "embedding_val": str(embedding), # or cast appropriately depending on driver
            "limit": limit
        }).fetchall()
```
*Note: Consult specific driver docs for vector parameter binding, but aim for parameterized forms.*
