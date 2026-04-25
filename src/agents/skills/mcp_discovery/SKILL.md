---
name: mcp_discovery
description: Discover external MCP servers for missing capabilities.
category: infrastructure
tier: fast
input_schema:
  type: object
  properties:
    user_id: {type: string}
    query: {type: string, description: "Query for the missing capability (e.g. 'Twitter posting')"}
  required: [user_id, query]
metadata:
  openclaw:
    os: ["linux", "darwin"]
---

# Skill: mcp_discovery

This skill identifies external MCP (Model Context Protocol) servers that can fulfill tasks the agent currently lacks internal skills for.

### Usage
Use this skill when the `GapDetector` identifies a missing capability or when specifically looking for third-party integrations.

### Required Arguments for run_script:
Assistant: <tool_code>run_script(skill_name="mcp_discovery", args=["--user_id", "{{user_id}}", "--query", "Twitter posting service"])</tool_code>
