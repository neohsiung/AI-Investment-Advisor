import pandas as pd
from src.data.database import get_db_connection
from sqlalchemy import text
import uuid
import datetime
import os

class TradeIngestor:
    """
    負責將外部交易數據 (CSV) 匯入至資料庫。
    Support Brokers: Simple, Robinhood, IBKR.
    """
    def __init__(self, db_path="data/portfolio.db"):
        self.db_path = db_path

    def ingest_csv(self, file_path, broker, user_id):
        """
        Parses CSV and inserts trades into the database.
        Supported brokers: 'simple', 'robinhood', 'ibkr'
        """
        try:
            broker = broker.lower()
            if broker not in ['simple', 'robinhood', 'ibkr']:
                 raise ValueError(f"Unsupported broker: {broker}")

            df = pd.read_csv(file_path)

            if broker == 'simple':
                self._ingest_simple(df, user_id)
            elif broker == 'robinhood':
                self._ingest_robinhood(df, user_id)
            elif broker == 'ibkr':
                self._ingest_ibkr(df, user_id)

        except Exception as e:
            # Re-raise to let UI handle it
            raise e

    def _ingest_simple(self, df, user_id):
        # Validate columns
        required_cols = ['ticker', 'quantity', 'cost']
        for col in required_cols:
            if col not in df.columns:
                raise ValueError(f"Missing required column: {col}")

        # Columns: ticker, quantity, cost (avg cost)
        # We model this as a BUY transaction with price = cost
        with get_db_connection(self.db_path) as conn:
            for _, row in df.iterrows():
                ticker = str(row['ticker']).upper().strip()
                quantity = float(row['quantity'])
                price = float(row['cost'])
                amount = quantity * price

                query = text("""
                    INSERT INTO transactions (id, user_id, ticker, trade_date, action, quantity, price, fees, amount, source_file)
                    VALUES (:id, :user_id, :ticker, :trade_date, :action, :quantity, :price, :fees, :amount, 'csv_import')
                """)

                conn.execute(query, {
                    "id": str(uuid.uuid4()),
                    "user_id": user_id,
                    "ticker": ticker,
                    "trade_date": datetime.date.today().strftime("%Y-%m-%d"),
                    "action": "BUY",
                    "quantity": quantity,
                    "price": price,
                    "fees": 0,
                    "amount": amount
                })
            conn.commit()

    def _ingest_robinhood(self, df, user_id):
        # Normalize columns to lower case for easier matching
        df.columns = df.columns.str.lower()

        # Test input: state,symbol,date,side,quantity,price,fees
        with get_db_connection(self.db_path) as conn:
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
            conn.commit()

    def _ingest_ibkr(self, df, user_id):
        # Normalize columns
        df.columns = df.columns.str.lower()
        # Test input: Type,Symbol,Date/Time,Quantity,T. Price,Comm/Fee
        # Lowercase: type, symbol, date/time, quantity, t. price, comm/fee

        with get_db_connection(self.db_path) as conn:
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
            conn.commit()

    def ingest_manual_trade(self, ticker, date_str, action, quantity, price, fees=0, user_id=None):
        """
        Ingests a single manual trade.
        """
        amount = quantity * price

        with get_db_connection(self.db_path) as conn:
            query = text("""
                INSERT INTO transactions (id, user_id, ticker, trade_date, action, quantity, price, fees, amount, source_file)
                VALUES (:id, :user_id, :ticker, :trade_date, :action, :quantity, :price, :fees, :amount, 'manual_entry')
            """)

            conn.execute(query, {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "ticker": ticker.upper(),
                "trade_date": date_str,
                "action": action,
                "quantity": quantity,
                "price": price,
                "fees": fees,
                "amount": amount
            })
            conn.commit()
