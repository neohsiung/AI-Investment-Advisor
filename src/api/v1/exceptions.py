from fastapi import HTTPException, status

class BrokerNotConfiguredError(Exception):
    """Raised when broker credentials or base URL are missing/invalid."""
    pass

class BrokerDependencyError(Exception):
    """Raised when a third-party broker service fails or timeouts."""
    pass

class PortfolioDataError(Exception):
    """Raised when portfolio data is inconsistent or invalid."""
    pass
