# Data Layer Specification (v3)

> **Status**: Approved
> **Version**: 3.0 (Aligned with v3 Architecture)

## 1. Overview
The Data Layer is responsible for ingesting, normalizing, and storing financial data from various sources. v3 introduces `Event Logs` and `Manual Inputs` to support the Event-Driven Architecture.

## 2. Ingestion Architecture

We use an **Strategy Pattern** for ingestion:
*   `TradeIngestor` (Abstract Base Class): Defines the contract `ingest(file_path, user_id)`.
*   `RobinhoodIngestor`: Implements parsing for Robinhood CSVs.
*   `IBKRIngestor`: Implements parsing for Interactive Brokers CSVs.
*   `CSVIngestor`: Implements a simple standard CSV format.

### Factory
A `IngestorFactory` will route the request based on the provider string.

## 3. CSV Formats

### Simple Format
```csv
ticker,quantity,cost
AAPL,10,150.0
TSLA,5,200.0
```

### Robinhood Format (Standard Export)
Keys often include: `state`, `symbol`, `date`, `side`, `quantity`, `price`, `fees`.

### IBKR Format (Flex Query)
Keys often include: `Type`, `Symbol`, `Date/Time`, `Quantity`, `T. Price`, `Comm/Fee`.

## 4. Database Schema (v3)

Defined in `src/data/database.py`. Key additions:
*   **event_logs**: For `LightCIO` to log ignored events.
*   **manual_inputs**: For users to inject PDF/Text for analysis.
*   **agent_knowledge**: For persisting specific insights.
