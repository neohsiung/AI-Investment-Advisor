import pytest
from sqlalchemy import text
from src.services.attribution_analyzer import AttributionAnalyzer
from src.data.database import get_db_connection

def test_attribution_analyzer_logic():
    # Setup test data
    from src.repositories.agent_repository import AlchemyAgentRepository
    AlchemyAgentRepository() # Ensure the agent_performance table is initialized

    conn = get_db_connection()
    try:
        # Clear existing test data
        conn.execute(text("DELETE FROM agent_performance"))
        
        # Insert Mock Agents
        # FastRisk: High win rate (80%) -> Should increase weight
        conn.execute(text("""
            INSERT INTO agent_performance (agent_name, tier, weight, success_count, failure_count)
            VALUES ('FastRisk', 'fast', 1.0, 8, 2)
        """))
        
        # SmartFund: Low win rate (30%) -> Should decrease weight
        conn.execute(text("""
            INSERT INTO agent_performance (agent_name, tier, weight, success_count, failure_count)
            VALUES ('SmartFund', 'smart', 1.0, 3, 7)
        """))
        
        # AdvQuant: Not enough trades (3) -> Weight should remain close to 1.0
        conn.execute(text("""
            INSERT INTO agent_performance (agent_name, tier, weight, success_count, failure_count)
            VALUES ('AdvQuant', 'adv', 1.0, 2, 1)
        """))
        
        conn.commit()
    finally:
        conn.close()

    # Run Analyzer
    analyzer = AttributionAnalyzer()
    analyzer.run_attribution_cycle()
    
    # Verify Results
    conn = get_db_connection()
    try:
        results = conn.execute(text("SELECT agent_name, weight FROM agent_performance")).fetchall()
        weights = {row.agent_name: row.weight for row in results}
        
        print(f"Calibrated Weights: {weights}")
        
        assert weights['FastRisk'] > 1.0, "FastRisk weight should have increased"
        assert weights['SmartFund'] < 1.0, "SmartFund weight should have decreased"
        assert weights['AdvQuant'] == 1.0, "AdvQuant weight should be unchanged due to low trade count"
        
        print("✅ Attribution Analyzer Test Passed!")
    finally:
        conn.close()

if __name__ == "__main__":
    test_attribution_analyzer_logic()
