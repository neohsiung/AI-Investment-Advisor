from src.services.search_service import InternetSearchService
from src.services.market_data_service import MarketDataService
from src.repositories.transaction_repository import SqliteTransactionRepository
from src.utils.logger import setup_logger

logger = setup_logger("SkillRegistry")

# Lazy Loading to avoid circular imports or heavy init at module level
_search_service = None
_market_service = None
_tx_repo = None

def get_search_service():
    global _search_service
    if not _search_service:
        _search_service = InternetSearchService()
    return _search_service

def get_market_service():
    global _market_service
    if not _market_service:
        _market_service = MarketDataService()
    return _market_service

def get_tx_repo():
    global _tx_repo
    if not _tx_repo:
        _tx_repo = SqliteTransactionRepository()
    return _tx_repo

# --- Implementations ---

def search_web(query: str) -> str:
    """Executes web search."""
    try:
        svc = get_search_service()
        results = svc.search_financial_context(query, max_results=3)
        if not results:
            return "No results found."
        
        # Format as string
        out = ""
        for r in results:
            out += f"- {r.get('title')}: {r.get('snippet')} ({r.get('link')})\n"
        return out
    except Exception as e:
        logger.error(f"Skill search_web failed: {e}")
        return f"Error: {e}"

def get_market_data(ticker: str) -> str:
    """Fetches market data."""
    try:
        svc = get_market_service()
        # Use get_market_context which returns a dict keyed by ticker
        context = svc.get_market_context([ticker], enrich=False)
        if exclude_ticker := context.get(ticker):
            # Basic formatting
            price_data = exclude_ticker.get("price_data", {})
            close_prices = price_data.get("close", [])
            price = close_prices[-1] if close_prices else "N/A"
            indicators = exclude_ticker.get("indicators", {})
            return f"Price: {price}\nIndicators: {indicators}"
        return "No data found."
    except Exception as e:
        logger.error(f"Skill get_market_data failed: {e}")
        return f"Error: {e}"

def get_portfolio(user_id: str) -> str:
    """Fetches portfolio summary."""
    try:
        repo = get_tx_repo()
        summary = repo.get_holdings_summary(user_id)
        leverage = repo.get_latest_leverage(user_id)
        return f"Leverage: {leverage:.2f}\nHoldings: {summary}"
    except Exception as e:
        logger.error(f"Skill get_portfolio failed: {e}")
        return f"Error: {e}"

# --- Registry ---

SKILL_IMPLEMENTATIONS = {
    "search_web": search_web,
    "get_market_data": get_market_data,
    "get_portfolio": get_portfolio
}

def bind_skills_to_agent(agent):
    """
    Binds implemented skills to the agent's McpServer.
    """
    from src.tools.mcp_server import McpTool
    
    # Check loaded skills in agent
    if hasattr(agent, 'skill_loader') and agent.skill_loader.skills:
        for name, skill_def in agent.skill_loader.skills.items():
            if name in SKILL_IMPLEMENTATIONS:
                # Register
                func = SKILL_IMPLEMENTATIONS[name]
                tool = McpTool(name=name, func=func, description=skill_def.description)
                agent.register_tool(tool)
                agent.logger.info(f"SkillRegistry: Bound '{name}' to agent.")
