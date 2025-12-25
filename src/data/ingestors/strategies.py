import pandas as pd
import uuid
import datetime
from sqlalchemy import text
from src.data.database import get_db_connection
from .base import BaseIngestor
import json

class SimpleIngestor(BaseIngestor):
    def ingest(self, df: pd.DataFrame, user_id: str) -> None:
        # Normalize columns
        df.columns = df.columns.str.lower().str.strip()

        # Validate required columns
        required_cols = ['ticker', 'quantity', 'price']
        # 'cost' is alias for 'price', support both for backward compatibility
        if 'cost' in df.columns and 'price' not in df.columns:
            df.rename(columns={'cost': 'price'}, inplace=True)

        for col in required_cols:
            if col not in df.columns:
                raise ValueError(f"Missing required column: {col} (Supports: ticker, quantity, price, action, date, fees)")

        with get_db_connection(self.db_path) as conn:
            with conn.begin():
                for _, row in df.iterrows():
                    ticker = str(row['ticker']).upper().strip()
                    try:
                        quantity = float(row['quantity'])
                        price = float(row['price'])
                    except ValueError:
                         continue

                    # Optional fields with defaults
                    fees = float(row.get('fees', 0))
                    date_str = row.get('date', datetime.date.today().strftime("%Y-%m-%d"))
                    action = str(row.get('action', 'BUY')).upper().strip()
                    leverage = float(row.get('leverage', 1.0))

                    # Basic validation for Action
                    valid_actions = ['BUY', 'SELL', 'DIVIDEND', 'DEPOSIT', 'WITHDRAW']
                    if action not in valid_actions:
                        action = 'BUY'
                    
                    amount = quantity * price
                    
                    # Store extras in raw_data
                    raw_data = json.dumps({"leverage": leverage, "source": "csv_simple"})

                    query = text("""
                        INSERT INTO transactions (id, user_id, ticker, trade_date, action, quantity, price, fees, amount, source_file, raw_data)
                        VALUES (:id, :user_id, :ticker, :trade_date, :action, :quantity, :price, :fees, :amount, 'csv_import', :raw_data)
                    """)

                    conn.execute(query, {
                        "id": str(uuid.uuid4()),
                        "user_id": user_id,
                        "ticker": ticker,
                        "trade_date": date_str,
                        "action": action,
                        "quantity": quantity,
                        "price": price,
                        "fees": fees,
                        "amount": amount,
                        "raw_data": raw_data
                    })

class RobinhoodIngestor(BaseIngestor):
    def ingest(self, df: pd.DataFrame, user_id: str) -> None:
        # Normalize columns to lower case for easier matching
        df.columns = df.columns.str.lower()

        # Test input: state,symbol,date,side,quantity,price,fees
        with get_db_connection(self.db_path) as conn:
            with conn.begin():
                for _, row in df.iterrows():
                    # Robinhood export often has 'symbol', but sometimes 'ticker'
                    if 'symbol' in df.columns:
                         ticker = row['symbol']
                    elif 'ticker' in df.columns:
                         ticker = row['ticker']
                    else:
                        continue # Skip unrelated rows

                    date_str = row.get('date', datetime.date.today().strftime("%Y-%m-%d"))
                    side = row.get('side', 'buy')
                    
                    try:
                        qty = float(row.get('quantity', 0))
                        price = float(row.get('price', 0))
                        fees = float(row.get('fees', 0))
                    except ValueError:
                        continue # Skip invalid numbers

                    if qty == 0: continue

                    action = 'BUY' if str(side).lower() == 'buy' else 'SELL'
                    amount = qty * price

                    query = text("""
                        INSERT INTO transactions (id, user_id, ticker, trade_date, action, quantity, price, fees, amount, source_file)
                        VALUES (:id, :user_id, :ticker, :trade_date, :action, :quantity, :price, :fees, :amount, 'robinhood_import')
                    """)

                    conn.execute(query, {
                        "id": str(uuid.uuid4()),
                        "user_id": user_id,
                        "ticker": ticker.upper(),
                        "trade_date": date_str,
                        "action": action,
                        "quantity": qty,
                        "price": price,
                        "fees": fees,
                        "amount": amount
                    })

class IBKRIngestor(BaseIngestor):
    def ingest(self, df: pd.DataFrame, user_id: str) -> None:
         # Normalize columns
        df.columns = df.columns.str.lower()
        # Test input: Type,Symbol,Date/Time,Quantity,T. Price,Comm/Fee
        # Lowercase: type, symbol, date/time, quantity, t. price, comm/fee

        with get_db_connection(self.db_path) as conn:
            with conn.begin():
                for _, row in df.iterrows():
                    row_type = row.get('type') # Trade, Dividend, ...
                    ticker = row.get('symbol')
                    
                    # IBKR Date/Time format: "2023-10-27, 09:30:00" -> extract date
                    raw_date = str(row.get('date/time', '')).split(',')[0]
                    date_str = raw_date if raw_date else datetime.date.today().strftime("%Y-%m-%d")

                    if row_type == 'Trade':
                        try:
                            qty = float(row.get('quantity', 0))
                            price = float(row.get('t. price', 0))
                            fees = float(row.get('comm/fee', 0))
                        except ValueError:
                            continue 

                        action = 'BUY' if qty > 0 else 'SELL'
                        amount = abs(qty * price)
                        
                        # IBKR represents sell as negative qty, we store absolute quantity
                        qty = abs(qty)
                        fees = abs(fees) # IBKR often shows fees as negative numbers (expense)

                    elif row_type == 'Dividend':
                        qty = 0
                        price = 0
                        fees = 0
                        action = 'DIVIDEND'
                        amount = float(row.get('amount', row.get('comm/fee', 0))) # Sometimes in Amount column or Fee column depending on report
                        # Logic might need tuning based on exact report CSV
                    else:
                        continue

                    if not ticker: continue

                    query = text("""
                        INSERT INTO transactions (id, user_id, ticker, trade_date, action, quantity, price, fees, amount, source_file)
                        VALUES (:id, :user_id, :ticker, :trade_date, :action, :quantity, :price, :fees, :amount, 'ibkr_import')
                    """)

                    conn.execute(query, {
                        "id": str(uuid.uuid4()),
                        "user_id": user_id,
                        "ticker": ticker.upper(),
                        "trade_date": date_str,
                        "action": action,
                        "quantity": qty,
                        "price": price,
                        "fees": fees,
                        "amount": amount
                    })
