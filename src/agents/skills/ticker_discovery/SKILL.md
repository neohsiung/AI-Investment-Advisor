# Ticker Discovery Skill (ticker_discovery)

Scans the internet for high-potential ticker candidates based on a specific strategy or sector focus.

## Purpose
- Enables the "Ticker Discovery" phase of Capital Deployment (Phase 1).
- Provides a dynamic list of investment candidates beyond a static shortlist.
- Uses web search and LLM extraction to identify symbols mentioned in recent financial news/analysis.

## Usage
Used by the `SwarmOrchestrator` or called directly by the `cash_deployment` skill.

### Inputs
- `strategy` (Optional): e.g., "growth", "value", "dividend", "momentum".
- `sectors` (Optional): e.g., ["technology", "healthcare"].

### Output
JSON string with a list of tickers, each including:
- `ticker`: Symbol (e.g., "NVDA")
- `reason`: Brief explanation for its inclusion.
- `source`: URL or context source.
