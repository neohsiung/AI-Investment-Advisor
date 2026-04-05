---
name: knowledge_vault
description: Persistent Knowledge Vault (RAG 2.0) interface for agents to save, query, and prune long-term memories.
metadata:
  openclaw:
    os: [linux, darwin]
---

# Knowledge Vault

Provides Level 4 Autonomy capabilities by allowing agents to read and write persistent, vector-searchable memories across sessions.

## When to Use

- When an agent detects a significant 'Regime Shift' or forms a 'Key Takeaway' that should be remembered for future analysis.
- When an agent needs historical context about a specific topic (e.g., 'What was the sentiment on tech stocks during the last rate hike?').
