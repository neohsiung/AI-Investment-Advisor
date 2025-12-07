import pandas as pd
from src.database import get_db_connection
from datetime import datetime
from sqlalchemy import text

class LeverageCalculator:
    def __init__(self, db_path="data/portfolio.db"):
        self.db_path = db_path

    def calculate_metrics(self, current_prices, user_id):
        """
        計算槓桿水位相關指標
        current_prices: dict, {ticker: price}
        user_id: str
        return: dict, {tnv, nlv, leverage_ratio, margin_level}
        """
        conn = get_db_connection(self.db_path)
        
        # 1. 計算總名義價值 (TNV)
        query = text("SELECT ticker, SUM(CASE WHEN action='BUY' THEN quantity WHEN action='SELL' THEN -quantity ELSE 0 END) as net_qty FROM transactions WHERE user_id = :user_id GROUP BY ticker")
        positions = pd.read_sql(query, conn, params={"user_id": user_id})
        
        tnv = 0.0
        portfolio_value = 0.0
        
        for _, row in positions.iterrows():
            ticker = row['ticker']
            qty = row['net_qty']
            if qty == 0:
                continue
            
            price = current_prices.get(ticker, 0.0)
            market_val = qty * price
            tnv += abs(market_val) # 名義價值取絕對值總和
            portfolio_value += market_val # 投資組合市值 (Long - Short)

        # 2. 計算淨清算價值 (NLV)
        # Cash Balance = Sum(Deposits) - Sum(Withdrawals) + Sum(Realized P&L) ... 
        
        cash_query = text("SELECT SUM(amount) FROM cash_flows WHERE user_id = :user_id")
        result = conn.execute(cash_query, {"user_id": user_id}).fetchone()
        cash_flow_sum = result[0] if result and result[0] is not None else 0.0
        
        trans_query = text("SELECT action, amount FROM transactions WHERE user_id = :user_id")
        trans_df = pd.read_sql(trans_query, conn, params={"user_id": user_id})
        
        trans_cash_impact = 0.0
        for _, row in trans_df.iterrows():
            if row['action'] == 'BUY':
                trans_cash_impact -= row['amount']
            elif row['action'] == 'SELL':
                trans_cash_impact += row['amount']
            
        cash_balance = cash_flow_sum + trans_cash_impact
        nlv = cash_balance + portfolio_value
        
        # 3. 槓桿比率
        leverage_ratio = tnv / nlv if nlv > 0 else float('inf')
        
        conn.close()
        
        return {
            "tnv": tnv,
            "nlv": nlv,
            "cash_balance": cash_balance,
            "leverage_ratio": leverage_ratio
        }

class ROIEngine:
    def __init__(self, db_path="data/portfolio.db"):
        self.db_path = db_path
        
    def calculate_roi(self, nlv, user_id):
        """
        計算簡單 ROI (Return on Investment)
        ROI = (NLV - Net Invested Capital) / Net Invested Capital
        """
        conn = get_db_connection(self.db_path)
        
        # Net Invested Capital = Deposits - Withdrawals
        query = text("SELECT SUM(CASE WHEN type='DEPOSIT' THEN amount WHEN type='WITHDRAWAL' THEN -amount ELSE 0 END) FROM cash_flows WHERE user_id = :user_id")
        result = conn.execute(query, {"user_id": user_id}).fetchone()
        net_invested = result[0] if result and result[0] is not None else 0.0
        
        conn.close()
        
        if net_invested == 0:
            return 0.0
            
        profit = nlv - net_invested
        roi = (profit / net_invested) * 100
        
        return roi

class SnapshotRecorder:
    def __init__(self, db_path=None):
        self.db_path = db_path

    def record_daily_snapshot(self, nlv, cash_balance, user_id):
        """記錄每日資產快照"""
        conn = get_db_connection(self.db_path)
        
        # 計算總投入資本
        query = text("SELECT SUM(CASE WHEN type='DEPOSIT' THEN amount WHEN type='WITHDRAWAL' THEN -amount ELSE 0 END) FROM cash_flows WHERE user_id = :user_id")
        result = conn.execute(query, {"user_id": user_id}).fetchone()
        net_invested = result[0] if result and result[0] is not None else 0.0
        
        pnl = nlv - net_invested
        from src.utils.time_utils import get_current_date_str
        date_str = get_current_date_str()
        
        # 使用 REPLACE INTO 確保同一天只會有一筆紀錄 (更新最新狀態)
        conn.execute(text('''
            REPLACE INTO daily_snapshots (date, user_id, total_nlv, cash_balance, invested_capital, pnl)
            VALUES (:date, :user_id, :nlv, :cash_balance, :invested_capital, :pnl)
        '''), {
            "date": date_str,
            "user_id": user_id,
            "nlv": nlv,
            "cash_balance": cash_balance,
            "invested_capital": net_invested,
            "pnl": pnl
        })
        
        conn.commit()
        conn.close()
        print(f"Recorded snapshot for {user_id} on {date_str}: NLV=${nlv:,.2f}, PnL=${pnl:,.2f}")

from src.market_data import MarketDataService

def update_daily_snapshot(db_path="data/portfolio.db", user_id=None):
    """
    重新計算並更新今日績效快照 (Helper Function)
    使用真實市場數據
    """
    if not user_id:
        return # Skip if no user_id provided
        
    conn = get_db_connection(db_path)
    # 查詢活躍持倉 (Quantity != 0)
    query = text("""
        SELECT ticker, SUM(CASE WHEN action='BUY' THEN quantity WHEN action='SELL' THEN -quantity ELSE 0 END) as net_qty 
        FROM transactions 
        WHERE user_id = :user_id
        GROUP BY ticker 
        HAVING net_qty > 0.0001
    """)
    df = pd.read_sql(query, conn, params={"user_id": user_id})
    conn.close()
    
    active_tickers = df['ticker'].tolist() if not df.empty else []
    
    # 獲取真實股價
    market_service = MarketDataService()
    current_prices = market_service.get_current_prices(active_tickers)
    
    calc = LeverageCalculator(db_path=db_path)
    # Need to handle empty prices gracefully inside or here
    metrics = calc.calculate_metrics(current_prices, user_id)
    
    recorder = SnapshotRecorder(db_path=db_path)
    recorder.record_daily_snapshot(metrics['nlv'], metrics['cash_balance'], user_id)

class PnLCalculator:
    def __init__(self, db_path="data/portfolio.db"):
        self.db_path = db_path

    def calculate_breakdown(self, current_prices, user_id):
        """
        計算損益細分 (已實現 vs 未實現)
        採用平均成本法 (Average Cost Method)
        """
        conn = get_db_connection(self.db_path)
        # 取得所有交易，按時間排序
        query = text("SELECT ticker, action, quantity, price, fees FROM transactions WHERE user_id = :user_id ORDER BY trade_date ASC")
        transactions = pd.read_sql(query, conn, params={"user_id": user_id})
        conn.close()

        portfolio = {} # {ticker: {'qty': 0, 'avg_cost': 0, 'realized_pnl': 0}}
        
        total_realized_pnl = 0.0
        
        for _, row in transactions.iterrows():
            ticker = row['ticker']
            action = row['action']
            qty = row['quantity']
            price = row['price']
            fees = row['fees']
            
            if ticker not in portfolio:
                portfolio[ticker] = {'qty': 0.0, 'avg_cost': 0.0, 'realized_pnl': 0.0}
            
            pos = portfolio[ticker]
            
            if action == 'BUY':
                total_cost = (pos['qty'] * pos['avg_cost']) + (qty * price) + fees
                new_qty = pos['qty'] + qty
                pos['avg_cost'] = total_cost / new_qty if new_qty > 0 else 0.0
                pos['qty'] = new_qty
                
            elif action == 'SELL':
                trade_pnl = (price - pos['avg_cost']) * qty - fees
                pos['realized_pnl'] += trade_pnl
                total_realized_pnl += trade_pnl
                pos['qty'] -= qty
                if pos['qty'] < 0: pos['qty'] = 0 

        # 計算未實現損益
        total_unrealized_pnl = 0.0
        breakdown = {}
        
        for ticker, pos in portfolio.items():
            if pos['qty'] > 0.0001: # 忽略微小誤差
                curr_price = current_prices.get(ticker, 0.0)
                # 未實現 = (現價 - 平均成本) * 持倉數
                unrealized = (curr_price - pos['avg_cost']) * pos['qty']
                total_unrealized_pnl += unrealized
                
                breakdown[ticker] = {
                    'qty': pos['qty'],
                    'avg_cost': pos['avg_cost'],
                    'current_price': curr_price,
                    'realized': pos['realized_pnl'],
                    'unrealized': unrealized,
                    'total': pos['realized_pnl'] + unrealized
                }
            elif abs(pos['realized_pnl']) > 0:
                 # 已清倉但有歷史損益
                 breakdown[ticker] = {
                    'qty': 0,
                    'avg_cost': 0,
                    'current_price': current_prices.get(ticker, 0.0),
                    'realized': pos['realized_pnl'],
                    'unrealized': 0,
                    'total': pos['realized_pnl']
                }

        return {
            "realized": total_realized_pnl,
            "unrealized": total_unrealized_pnl,
            "total": total_realized_pnl + total_unrealized_pnl,
            "details": breakdown
        }
