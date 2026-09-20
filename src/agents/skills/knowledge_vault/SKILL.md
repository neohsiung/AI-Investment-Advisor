---
name: knowledge_vault
version: 1.0.0
description: Persistent Knowledge Vault (RAG 2.0) interface for agents to save, query, and prune long-term memories.
category: core
tier: fast
tags: [memory, rag]
platform: [linux, darwin]
metadata:
  openclaw:
    os: [linux, darwin]
input_schema:
  type: object
  properties:
    action:
      type: string
      description: "The action to perform: 'save', 'query', or 'prune'."
    content:
      type: string
      description: "The text content to save. Required for 'save'."
    query_term:
      type: string
      description: "The term/question to search for. Required for 'query'."
    category:
      type: string
      description: "The category of the knowledge (e.g., 'macro', 'sentiment', 'risk')."
    limit:
      type: integer
      description: "Max results for query. Default 5."
  required: [action]
output_schema:
  type: string
  description: "Result of the action (JSON string or status message)."
---

# Knowledge Vault

Provides Level 4 Autonomy capabilities by allowing agents to read and write persistent, vector-searchable memories across sessions.

## When to Use

- When an agent detects a significant 'Regime Shift' or forms a 'Key Takeaway' that should be remembered for future analysis.
- When an agent needs historical context about a specific topic (e.g., 'What was the sentiment on tech stocks during the last rate hike?').
