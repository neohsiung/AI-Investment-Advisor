import pandas as pd
from src.database import get_db_connection
from sqlalchemy import text
import uuid
import datetime

class TradeIngestor:
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
                ticker = row['ticker'].upper()
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
                if 'symbol' in df.columns:
                     ticker = row['symbol']
                     date_str = row['date']
                     side = row['side']
                     qty = float(row['quantity'])
                     price = float(row['price'])
                     fees = float(row['fees'])
                else:
                    continue

                action = 'BUY' if str(side).lower() == 'buy' else 'SELL'
                amount = qty * price 
                
                query = text("""
                    INSERT INTO transactions (id, user_id, ticker, trade_date, action, quantity, price, fees, amount, source_file)
                    VALUES (:id, :user_id, :ticker, :trade_date, :action, :quantity, :price, :fees, :amount, 'robinhood_import')
                """)
                
                conn.execute(query, {
                    "id": str(uuid.uuid4()),
                    "user_id": user_id,
                    "ticker": ticker,
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
                row_type = row.get('type')
                ticker = row.get('symbol')
                date_str = row.get('date/time')
                
                if row_type == 'Trade':
                    qty = float(row['quantity'])
                    price = float(row.get('t. price', 0))
                    fees = float(row.get('comm/fee', 0))
                    action = 'BUY' if qty > 0 else 'SELL'
                    amount = abs(qty * price)
                    
                elif row_type == 'Dividend':
                    qty = 0
                    price = 0
                    fees = 0 
                    action = 'DIVIDEND'
                    amount = float(row.get('comm/fee', 0))
                else:
                    continue
                    
                query = text("""
                    INSERT INTO transactions (id, user_id, ticker, trade_date, action, quantity, price, fees, amount, source_file)
                    VALUES (:id, :user_id, :ticker, :trade_date, :action, :quantity, :price, :fees, :amount, 'ibkr_import')
                """)
                
                conn.execute(query, {
                    "id": str(uuid.uuid4()),
                    "user_id": user_id,
                    "ticker": ticker,
                    "trade_date": date_str,
                    "action": action,
                    "quantity": abs(qty),
                    "price": price,
                    "fees": abs(fees),
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
                "ticker": ticker,
                "trade_date": date_str,
                "action": action,
                "quantity": quantity,
                "price": price,
                "fees": fees,
                "amount": amount
            })
            conn.commit()
