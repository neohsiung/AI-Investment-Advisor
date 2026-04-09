# Skill: extract_actions

Modular extraction of structured trade orders from investment council decisions.

## Description
This skill transforms unstructured AI-generated text decisions into machine-readable JSON format. It is particularly designed for the "ReAct" level of the Multi-Tier Agent Swarm to convert high-level decisions into actionable database entries.

## Usage
Used by:
- `AutomatedTradingService`: During the automated rebalancing phase.
- `SentinelService`: When processing safety-check results.

## Pattern
This skill replaces the legacy `ActionExtractorAgent` to reduce hardcoding and improve maintainability.
