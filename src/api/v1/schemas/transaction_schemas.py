from pydantic import BaseModel, Field, validator
from typing import List, Optional
from datetime import datetime

class TransactionBase(BaseModel):
    """Base fields for a financial transaction."""
    ticker: str = Field(..., description="Stock or asset ticker (e.g., NVDA)")
    action: str = Field(..., description="BUY or SELL")
    quantity: float = Field(..., gt=0, description="Number of units traded")
    price: float = Field(..., gt=0, description="Execution price per unit")
    fees: float = Field(default=0.0, description="Transaction fees")
    date: str = Field(..., description="Transaction date in YYYY-MM-DD format")

    @validator('ticker')
    def ticker_uppercase(cls, v):
        return v.upper()

    @validator('action')
    def action_caps(cls, v):
        return v.upper()

class TransactionCreateRequest(TransactionBase):
    """Request schema for manually adding a trade."""
    pass

class TransactionRecord(TransactionBase):
    """Detailed record stored in the database."""
    id: str = Field(..., description="Unique transaction ID")
    created_at: Optional[datetime] = None

class TransactionListResponse(BaseModel):
    """Standardized response for transaction history."""
    status: str = "success"
    data: List[TransactionRecord]

class TransactionActionResponse(BaseModel):
    """Response for single actions (Add/Delete)."""
    status: str = "success"
    message: str
