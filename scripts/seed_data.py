
from src.data.database import init_db
from src.services.transaction_service import TransactionService
from datetime import datetime

init_db()
service = TransactionService(user_id="test_user")
success, msg = service.add_manual_trade(
    ticker="AAPL",
    date_str=datetime.now().strftime("%Y-%m-%d"),
    action="BUY",
    quantity=10,
    price=150.0,
    fees=0
)
print(f"Seed Result: {success} - {msg}")
