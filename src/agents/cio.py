import pandas as pd
from src.database import get_db_connection
from .base_agent import BaseAgent

class CIOAgent(BaseAgent):
    def __init__(self, use_cache=True):
        super().__init__(name="CIO", prompt_path="prompts/cio_agent.txt", use_cache=use_cache, ttl_hours=24)
        # 常見 ETF 清單 (可擴充)
        self.etf_list = {
            "SPY", "QQQ", "VOO", "IWM", "VT", "BND", "TLT", "VTI", "VEA", "VWO", 
            "IVV", "AGG", "GLD", "SLV", "ARKK", "SOXX", "XLE", "XLF", "XLK", "XLV"
        }

    def _get_non_etf_holdings_count(self):
        """計算非 ETF 的持倉數量"""
        try:
            conn = get_db_connection()
            # 查詢目前持倉 (Quantity != 0)
            query = """
                SELECT ticker, SUM(CASE WHEN action='BUY' THEN quantity WHEN action='SELL' THEN -quantity ELSE 0 END) as net_qty 
                FROM transactions 
                GROUP BY ticker 
                HAVING net_qty > 0.0001
            """
            df = pd.read_sql(query, conn)
            conn.close()
            
            if df.empty:
                return 0, []
            
            tickers = df['ticker'].tolist()
            non_etf_tickers = [t for t in tickers if t not in self.etf_list]
            
            return len(non_etf_tickers), non_etf_tickers
        except Exception as e:
            print(f"[CIO] Error calculating holdings: {e}")
            return 0, []

    def run(self, context):
        """
        context: {
            "momentum_reports": [...],
            "fundamental_reports": [...],
            "macro_report": "...",
            "leverage_ratio": 1.2
        }
        """
        macro = context.get("macro_report", "")
        leverage = context.get("leverage_ratio", 1.0)
        
        # 計算非 ETF 持倉
        non_etf_count, non_etf_list = self._get_non_etf_holdings_count()
        
        user_prompt = f"""
        Macro Outlook:
        {macro}
        
        Portfolio Leverage: {leverage}x
        Non-ETF Holdings Count: {non_etf_count} (Tickers: {', '.join(non_etf_list)})
        
        Team Reports:
        {context.get("momentum_reports")}
        {context.get("fundamental_reports")}
        """
        
        response = self._mock_llm_call(user_prompt, self.system_prompt)
        
        # 若使用 Mock，回傳更豐富的 Mock Response 以符合新格式
        if "Mock response" in response:
            return f"""
# 每週投資顧問報告
## 1. 執行摘要 (Executive Summary)
市場目前處於波動狀態，通膨數據略高於預期。投資組合槓桿比率為 {leverage}x，非 ETF 持倉數為 {non_etf_count} 檔，風險控制在合理範圍。

## 2. 持倉分析 (Portfolio Analysis)
目前持倉集中於科技股 ({', '.join(non_etf_list[:3])}...)，防禦性板塊配置較少。建議適度增加醫療保健或必需消費品比重。

## 3. 操作建議 (Actionable Advice)
- **AAPL**: 持有 (HOLD)。(基本面專家看好長期成長，但動能專家提示短期超買)。
- **NVDA**: 減碼 (TRIM)。(動能專家示警 RSI 過高)。
- **現金**: 維持當前水位，等待回調機會。

## 4. 潛力標的推薦 (New Opportunities)
- **JNJ (Johnson & Johnson)**: 推薦買入。基本面穩健，股息殖利率具吸引力，可平衡科技股波動。(基本面專家推薦)
- **XLP (Consumer Staples ETF)**: 考慮配置，作為防禦性部位。

*由 CIO Agent 生成 (Mock)*
            """
        
        return response
