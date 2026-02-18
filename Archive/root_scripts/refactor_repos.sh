#!/bin/bash

# Define the replacements as "FROM:TO" strings
REPLACEMENTS=(
    "SqliteTransactionRepository:AlchemyTransactionRepository"
    "TransactionRepositoryImpl:AlchemyTransactionRepository"
    "SqliteSettingsRepository:AlchemySettingsRepository"
    "SettingsRepositoryImpl:AlchemySettingsRepository"
    "SqliteSnapshotRepository:AlchemySnapshotRepository"
    "SnapshotRepositoryImpl:AlchemySnapshotRepository"
    "UserRepositoryImpl:AlchemyUserRepository"
    "RiskKeywordRepositoryImpl:AlchemyRiskKeywordRepository"
    "RiskKeywordRepository:AlchemyRiskKeywordRepository"
    "SqliteReportRepository:AlchemyReportRepository"
    "ReportRepositoryImpl:AlchemyReportRepository"
    "SentinelRepositoryImpl:AlchemySentinelRepository"
    "SentinelRepository:AlchemySentinelRepository"
    "AgentRepositoryImpl:AlchemyAgentRepository"
    "AgentRepository:AlchemyAgentRepository"
    "SqliteAgentStateRepository:AlchemyAgentStateRepository"
    "AgentStateRepositoryImpl:AlchemyAgentStateRepository"
    "SqliteDataRepository:AlchemyDataRepository"
    "DataRepositoryImpl:AlchemyDataRepository"
    "SqliteFeedbackRepository:AlchemyFeedbackRepository"
    "FeedbackRepositoryImpl:AlchemyFeedbackRepository"
    "SqlitePromptRepository:AlchemyPromptRepository"
    "PromptRepositoryImpl:AlchemyPromptRepository"
    "SqliteMemoryRepository:AlchemyMemoryRepository"
    "MemoryRepositoryImpl:AlchemyMemoryRepository"
    "SqliteVectorRepository:AlchemyVectorRepository"
    "VectorRepositoryImpl:AlchemyVectorRepository"
    "VectorRepository:AlchemyVectorRepository"
    "VerificationRepositoryImpl:AlchemyVerificationRepository"
    "VerificationRepository:AlchemyVerificationRepository"
    "MarketDataRepositoryImpl:AlchemyMarketDataRepository"
    "MarketDataRepository:AlchemyMarketDataRepository"
)

# Target directory
TARGET_DIR="src"

# Iterate over each replacement
for ENTRY in "${REPLACEMENTS[@]}"; do
    FROM="${ENTRY%%:*}"
    TO="${ENTRY##*:}"
    echo "Replacing $FROM with $TO..."
    
    # Use find and sed to replace in all files
    # -i '' is for Mac sed compatibility
    find "$TARGET_DIR" -type f -name "*.py" -exec sed -i '' "s/\b$FROM\b/$TO/g" {} +
done

echo "Refactoring complete."
