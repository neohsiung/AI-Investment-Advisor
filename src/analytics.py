import pandas as pd
from src.database import get_db_connection
from datetime import datetime
from sqlalchemy import text

class LeverageCalculator:
    def __init__(self, db_path="data/portfolio.db"):
        self.db_path = db_path

    def calculate_metrics(self, current_prices):
        """
        計算槓桿水位相關指標
        current_prices: dict, {ticker: price}
        return: dict, {tnv, nlv, leverage_ratio, margin_level}
        """
        conn = get_db_connection(self.db_path)
        
        # 1. 計算總名義價值 (TNV)
        # 需從 Transactions 重建 Positions，或直接讀取 Positions 表 (若已維護)
        # 這裡簡單起見，從 Transactions 聚合
        query = "SELECT ticker, SUM(CASE WHEN action='BUY' THEN quantity WHEN action='SELL' THEN -quantity ELSE 0 END) as net_qty FROM transactions GROUP BY ticker"
        positions = pd.read_sql(query, conn)
        
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
        # NLV = Cash Balance + Portfolio Value
        # Cash Balance = Sum(Deposits) - Sum(Withdrawals) + Sum(Realized P&L) ... 
        # 簡化算法：NLV = Initial Cash + Net Cash Flow + Realized P&L + Unrealized P&L
        # 更簡單算法：NLV = Total Assets - Total Liabilities
        # 假設帳戶只有現金與證券：
        # Cash = Sum(CashFlows) - Sum(Transaction Costs)
        # Transaction Costs = Buy Amount + Fees (支出為負) ? 
        # 需仔細處理 Cash 計算。
        
        # 重新計算現金餘額:
        # Cash Flows 表: Deposits (+), Withdrawals (-)
        # Transactions 表: Buy (-Amount), Sell (+Amount), Fees (-)
        
        cash_query = text("SELECT SUM(amount) FROM cash_flows")
        cash_flow_sum = conn.execute(cash_query).fetchone()[0] or 0.0
        
        # Transactions amount: Buy is positive cost? Ingestor logic: amount = qty * price + fees.
        # Check ingestor: amount is positive.
        # We need to know direction.
        # Ingestor: action='BUY', amount=positive.
        # So Cash Change = -Amount (if Buy) or +Amount (if Sell).
        
        trans_query = "SELECT action, amount FROM transactions"
        trans_df = pd.read_sql(trans_query, conn)
        
        trans_cash_impact = 0.0
        for _, row in trans_df.iterrows():
            if row['action'] == 'BUY':
                trans_cash_impact -= row['amount']
            elif row['action'] == 'SELL':
                trans_cash_impact += row['amount']
            # Short/Cover logic similar to Sell/Buy
            
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
        
    def calculate_roi(self, nlv):
        """
        計算簡單 ROI (Return on Investment)
        ROI = (NLV - Net Invested Capital) / Net Invested Capital
        """
        conn = get_db_connection(self.db_path)
        
        # Net Invested Capital = Deposits - Withdrawals
        query = text("SELECT SUM(CASE WHEN type='DEPOSIT' THEN amount WHEN type='WITHDRAWAL' THEN -amount ELSE 0 END) FROM cash_flows")
        net_invested = conn.execute(query).fetchone()[0] or 0.0
        
        conn.close()
        
        if net_invested == 0:
            return 0.0
            
        profit = nlv - net_invested
        roi = (profit / net_invested) * 100
        
        return roi

class SnapshotRecorder:
    def __init__(self, db_path=None):
        self.db_path = db_path

    def record_daily_snapshot(self, nlv, cash_balance):
        """記錄每日資產快照"""
        conn = get_db_connection(self.db_path)
        
        # 計算總投入資本
        query = text("SELECT SUM(CASE WHEN type='DEPOSIT' THEN amount WHEN type='WITHDRAWAL' THEN -amount ELSE 0 END) FROM cash_flows")
        net_invested = conn.execute(query).fetchone()[0] or 0.0
        
        pnl = nlv - net_invested
        from src.utils.time_utils import get_current_date_str
        date_str = get_current_date_str()
        
        # 使用 REPLACE INTO 確保同一天只會有一筆紀錄 (更新最新狀態)
        conn.execute(text('''
            REPLACE INTO daily_snapshots (date, total_nlv, cash_balance, invested_capital, pnl)
            VALUES (:date, :nlv, :cash_balance, :invested_capital, :pnl)
        '''), {
            "date": date_str,
            "nlv": nlv,
            "cash_balance": cash_balance,
            "invested_capital": net_invested,
            "pnl": pnl
        })
        
        conn.commit()
        conn.close()
        print(f"Recorded snapshot for {date_str}: NLV=${nlv:,.2f}, PnL=${pnl:,.2f}")

from src.market_data import MarketDataService

def update_daily_snapshot(db_path="data/portfolio.db"):
    """
    重新計算並更新今日績效快照 (Helper Function)
    使用真實市場數據
    """
    conn = get_db_connection(db_path)
    # 查詢活躍持倉 (Quantity != 0)
    query = """
        SELECT ticker, SUM(CASE WHEN action='BUY' THEN quantity WHEN action='SELL' THEN -quantity ELSE 0 END) as net_qty 
        FROM transactions 
        GROUP BY ticker 
        HAVING net_qty > 0.0001
    """
    df = pd.read_sql(query, conn)
    conn.close()
    
    active_tickers = df['ticker'].tolist() if not df.empty else []
    
    # 獲取真實股價
    market_service = MarketDataService()
    current_prices = market_service.get_current_prices(active_tickers)
    
    # 若無持倉或無法獲取價格，仍需計算 (Cash Balance 可能有變動)
    # 但 LeverageCalculator 需要 prices 字典
    
    calc = LeverageCalculator(db_path=db_path)
    metrics = calc.calculate_metrics(current_prices)
    
    recorder = SnapshotRecorder(db_path=db_path)
    recorder.record_daily_snapshot(metrics['nlv'], metrics['cash_balance'])

class PnLCalculator:
    def __init__(self, db_path="data/portfolio.db"):
        self.db_path = db_path

    def calculate_breakdown(self, current_prices):
        """
        計算損益細分 (已實現 vs 未實現)
        採用平均成本法 (Average Cost Method)
        """
        conn = get_db_connection(self.db_path)
        # 取得所有交易，按時間排序
        query = "SELECT ticker, action, quantity, price, fees FROM transactions ORDER BY trade_date ASC"
        transactions = pd.read_sql(query, conn)
        conn.close()

        portfolio = {} # {ticker: {'qty': 0, 'avg_cost': 0, 'realized_pnl': 0}}
        
        total_realized_pnl = 0.0
        
        for _, row in transactions.iterrows():
            ticker = row['ticker']
            action = row['action']
            qty = row['quantity']
            price = row['price']
            fees = row['fees'] # Fees usually reduce realized PnL or increase cost basis
            
            if ticker not in portfolio:
                portfolio[ticker] = {'qty': 0.0, 'avg_cost': 0.0, 'realized_pnl': 0.0}
            
            pos = portfolio[ticker]
            
            if action == 'BUY':
                # 更新平均成本: (舊庫存 * 舊成本 + 新買入 * 買入價) / 總股數
                # 手續費計入成本
                total_cost = (pos['qty'] * pos['avg_cost']) + (qty * price) + fees
                new_qty = pos['qty'] + qty
                pos['avg_cost'] = total_cost / new_qty if new_qty > 0 else 0.0
                pos['qty'] = new_qty
                
            elif action == 'SELL':
                # 計算已實現損益: (賣出價 - 平均成本) * 賣出股數 - 手續費
                # 假設 FIFO 或 Average Cost，這裡用 Average Cost
                # 賣出不影響剩餘持倉的平均成本
                trade_pnl = (price - pos['avg_cost']) * qty - fees
                pos['realized_pnl'] += trade_pnl
                total_realized_pnl += trade_pnl
                pos['qty'] -= qty
                # Handle negative qty (Short selling) if needed, but assuming Long only for now or simple logic
                if pos['qty'] < 0: pos['qty'] = 0 # Prevent negative for simplicity unless shorting supported

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
