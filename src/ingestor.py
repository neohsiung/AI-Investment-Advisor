import pandas as pd
import json
import uuid
from datetime import datetime
from sqlalchemy import text
from pathlib import Path
from src.database import get_db_connection
from src.utils.time_utils import format_time

class TradeIngestor:
    def __init__(self, db_path="data/portfolio.db"):
        self.db_path = db_path

    def ingest_csv(self, file_path, broker="robinhood"):
        """攝取 CSV 檔案並寫入資料庫"""
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if broker.lower() == "robinhood":
            self._parse_robinhood(file_path)
        elif broker.lower() == "ibkr":
            self._parse_ibkr(file_path)
        elif broker.lower() == "simple":
            self._parse_simple_ticker(file_path)
        else:
            raise ValueError(f"Unsupported broker: {broker}")

    def _parse_simple_ticker(self, file_path):
        """解析簡易 Ticker 清單"""
        # 格式: ticker (必填), quantity (選填), cost (選填)
        df = pd.read_csv(file_path)
        conn = get_db_connection(self.db_path)
        
        # 標準化欄位名稱 (全部轉小寫)
        df.columns = [c.lower().strip() for c in df.columns]
        
        try:
            if 'ticker' not in df.columns:
                raise ValueError("Simple CSV must contain 'ticker' column")
                
            for _, row in df.iterrows():
                trans_id = str(uuid.uuid4())
                ticker = row['ticker'].upper()
                date_str = format_time()
                
                # 預設值
                quantity = float(row.get('quantity', 0))
                price = float(row.get('cost', 0))
                fees = 0.0
                
                action = 'BUY' if quantity > 0 else 'WATCH'
                amount = quantity * price
                
                conn.execute(text('''
                    INSERT INTO transactions (id, ticker, trade_date, action, quantity, price, fees, amount, source_file, raw_data)
                    VALUES (:id, :ticker, :trade_date, :action, :quantity, :price, :fees, :amount, :source_file, :raw_data)
                '''), {
                    "id": trans_id,
                    "ticker": ticker,
                    "trade_date": date_str,
                    "action": action,
                    "quantity": quantity,
                    "price": price,
                    "fees": fees,
                    "amount": amount,
                    "source_file": str(file_path),
                    "raw_data": json.dumps(row.to_dict())
                })
        except Exception as e:
            # conn.rollback() # If we were doing transaction management
            raise e
        finally:
            conn.commit()
            conn.close()
        print(f"Ingested Simple Ticker data from {file_path}")

    def _parse_robinhood(self, file_path):
        """解析 Robinhood CSV"""
        df = pd.read_csv(file_path)
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        # Robinhood CSV 欄位可能變動，這裡假設標準格式
        # 需過濾 state == 'filled'
        if 'state' in df.columns:
            df = df[df['state'] == 'filled']

        for _, row in df.iterrows():
            # 簡單範例邏輯, 需根據實際 CSV 調整
            trans_id = str(uuid.uuid4())
            ticker = row.get('symbol', 'UNKNOWN')
            date_str = row.get('date', format_time())
            action = row.get('side', 'buy').upper()
            quantity = float(row.get('quantity', 0))
            price = float(row.get('price', 0))
            fees = float(row.get('fees', 0))
            amount = quantity * price + fees # 簡化計算

            cursor.execute(text('''
                INSERT INTO transactions (id, ticker, trade_date, action, quantity, price, fees, amount, source_file, raw_data)
                VALUES (:id, :ticker, :trade_date, :action, :quantity, :price, :fees, :amount, :source_file, :raw_data)
            '''), {
                "id": trans_id,
                "ticker": ticker,
                "trade_date": date_str,
                "action": action,
                "quantity": quantity,
                "price": price,
                "fees": fees,
                "amount": amount,
                "source_file": file_path.name,
                "raw_data": json.dumps(row.to_dict())
            })

        conn.commit()
        conn.close()
        print(f"Ingested Robinhood data from {file_path}")

    def _parse_ibkr(self, file_path):
        """解析 IBKR CSV"""
        # IBKR CSV 通常有兩部分：Statement 與 Data，或直接是 Flex Query
        # 這裡假設是 Flex Query 格式，或標準 Activity Statement
        # 簡單起見，我們假設一個標準化的 CSV 結構，實際需根據 User 提供的範例調整
        
        df = pd.read_csv(file_path)
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        # 假設欄位: Symbol, Date/Time, Quantity, T. Price, Comm/Fee, Code, Type
        # 過濾出 Trades
        if 'Type' in df.columns:
            trades = df[df['Type'] == 'Trade']
            dividends = df[df['Type'] == 'Dividend']
        else:
            # Fallback logic or assume all are trades if simple format
            trades = df
            dividends = pd.DataFrame()

        for _, row in trades.iterrows():
            trans_id = str(uuid.uuid4())
            ticker = row.get('Symbol', 'UNKNOWN')
            date_str = row.get('Date/Time', format_time())
            quantity = float(row.get('Quantity', 0))
            price = float(row.get('T. Price', 0))
            fees = float(row.get('Comm/Fee', 0))
            
            # IBKR Quantity 負數為賣
            action = 'BUY' if quantity > 0 else 'SELL'
            quantity = abs(quantity)
            amount = quantity * price + fees # IBKR fees 通常是負數，這裡需確認正負號慣例
            
            # 修正 Amount 計算: IBKR 報表中，買入金額為負(支出)，賣出為正(收入)
            # 這裡我們儲存絕對值或依據 Schema 定義。
            # Schema amount: 總金額。
            
            cursor.execute(text('''
                INSERT INTO transactions (id, ticker, trade_date, action, quantity, price, fees, amount, source_file, raw_data)
                VALUES (:id, :ticker, :trade_date, :action, :quantity, :price, :fees, :amount, :source_file, :raw_data)
            '''), {
                "id": trans_id,
                "ticker": ticker,
                "trade_date": date_str,
                "action": action,
                "quantity": quantity,
                "price": price,
                "fees": fees,
                "amount": amount,
                "source_file": file_path.name,
                "raw_data": json.dumps(row.to_dict())
            })

        # 處理股息
        for _, row in dividends.iterrows():
            cash_id = str(uuid.uuid4())
            date_str = row.get('Date/Time', format_time())
            amount = float(row.get('Amount', 0))
            description = f"Dividend from {row.get('Symbol', 'UNKNOWN')}"
            
            cursor.execute(text('''
                INSERT INTO cash_flows (id, date, amount, type, description)
                VALUES (:id, :date, :amount, :type, :description)
            '''), {
                "id": cash_id,
                "date": date_str,
                "amount": amount,
                "type": 'DIVIDEND',
                "description": description
            })

        conn.commit()
        conn.close()
        print(f"Ingested IBKR data from {file_path}")

    def ingest_manual_trade(self, ticker, date, action, quantity, price, fees=0.0):
        """手動匯入單筆交易"""
        conn = get_db_connection(self.db_path)
        
        try:
            trans_id = str(uuid.uuid4())
            amount = quantity * price + fees
            
            # 建構類似原始數據的 JSON，方便除錯
            raw_data = {
                "source": "manual_entry",
                "ticker": ticker,
                "date": date,
                "action": action,
                "quantity": quantity,
                "price": price,
                "fees": fees
            }
            
            conn.execute(text('''
                INSERT INTO transactions (id, ticker, trade_date, action, quantity, price, fees, amount, source_file, raw_data)
                VALUES (:id, :ticker, :trade_date, :action, :quantity, :price, :fees, :amount, :source_file, :raw_data)
            '''), {
                "id": trans_id,
                "ticker": ticker,
                "trade_date": date,
                "action": action,
                "quantity": quantity,
                "price": price,
                "fees": fees,
                "amount": amount,
                "source_file": "MANUAL_ENTRY",
                "raw_data": json.dumps(raw_data)
            })
            
            conn.commit()
            print(f"Manually ingested trade: {action} {quantity} {ticker} @ {price}")
        finally:
            conn.close()

if __name__ == "__main__":
    # 測試用
    pass
