
import json
import uuid
from datetime import timedelta
from datetime import datetime
from src.utils.time_utils import format_time
from sqlalchemy import text
from src.database import get_db_connection

class RefinementEngine:
    def __init__(self, db_path="data/portfolio.db", config_path="agent_config.json"):
        self.db_path = db_path
        self.config_path = config_path
        self._load_config()

    def _load_config(self):
        try:
            with open(self.config_path, 'r') as f:
                self.config = json.load(f)
        except FileNotFoundError:
            self.config = {
                "MOMENTUM": {"weight": 1.0},
                "FUNDAMENTAL": {"weight": 1.0}
            }

    def _save_config(self):
        with open(self.config_path, 'w') as f:
            json.dump(self.config, f, indent=2)

    def record_recommendation(self, agent_name, ticker, signal, current_price):
        """記錄 Agent 的建議"""
        conn = get_db_connection(self.db_path)
        
        try:
            rec_id = str(uuid.uuid4())
            date_str = format_time()
            
            conn.execute(text('''
                INSERT INTO recommendations (id, date, agent, ticker, signal, price_at_signal)
                VALUES (:id, :date, :agent, :ticker, :signal, :price)
            '''), {
                "id": rec_id,
                "date": date_str,
                "agent": agent_name,
                "ticker": ticker,
                "signal": signal,
                "price": current_price
            })
            
            conn.commit()
        finally:
            conn.close()

    def run_attribution_analysis(self):
        """執行績效歸因分析 (Mock Implementation)"""
        print("Running Attribution Analysis...")
        conn = get_db_connection(self.db_path)
        
        # 1. 獲取 30 天前的建議
        # 這裡簡化邏輯，直接選取所有 outcome_score 為 0 的建議
        recs_result = conn.execute(text("SELECT * FROM recommendations WHERE outcome_score = 0"))
        recs = recs_result.mappings().fetchall()
        
        for rec in recs:
            # 2. 獲取當前價格 (Mock)
            # 實際應從 Market Data Agent 獲取
            current_price = rec['price_at_signal'] * 1.1 # 假設上漲 10%
            
            score = 0
            if rec['signal'] == 'BUY':
                if current_price > rec['price_at_signal'] * 1.05:
                    score = 1
                elif current_price < rec['price_at_signal'] * 0.95:
                    score = -1
            
            # 更新分數
            conn.execute(text("UPDATE recommendations SET outcome_score = :score WHERE id = :id"), {"score": score, "id": rec['id']})
            print(f"Updated score for {rec['agent']} on {rec['ticker']}: {score}")
            
        conn.commit()
        conn.close()
        
        # 3. 調整權重 (Mock Logic)
        # 實際應統計近期分數平均值
        self.config["MOMENTUM"]["weight"] = 1.1 # 假設表現良好
        self._save_config()
        print("Agent weights updated.")

if __name__ == "__main__":
    engine = RefinementEngine()
    # 測試記錄
    engine.record_recommendation("MOMENTUM", "AAPL", "BUY", 150.0)
    # 測試分析
    engine.run_attribution_analysis()
