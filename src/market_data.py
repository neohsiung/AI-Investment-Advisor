
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import os
import json
from sqlalchemy import text
from src.database import get_db_connection
from tenacity import retry, stop_after_attempt, wait_exponential
from src.utils.logger import setup_logger

class MarketDataService:
    def __init__(self, db_path=None):
        self.conn = get_db_connection(db_path)
        self.logger = setup_logger("MarketData")

    def get_current_prices(self, tickers):
        """
        獲取一組 Tickers 的最新價格
        tickers: list of str
        return: dict {ticker: price}
        """
        if not tickers:
            return {}
        
        try:
            # period="1d" 獲取最近一天數據
            data = yf.download(tickers, period="1d", auto_adjust=True, progress=False)
            
            prices = {}
            
            if len(tickers) == 1:
                # 單一 Ticker
                ticker = tickers[0]
                if not data.empty:
                    prices[ticker] = data['Close'].iloc[-1]
                    if isinstance(prices[ticker], pd.Series):
                         prices[ticker] = prices[ticker].item()
            else:
                # 多個 Ticker
                if not data.empty:
                    if 'Close' in data.columns:
                        close_data = data['Close']
                        for ticker in tickers:
                            if ticker in close_data.columns:
                                val = close_data[ticker].iloc[-1]
                                if pd.notna(val):
                                    prices[ticker] = val
            
            return prices

        except Exception as e:
            self.logger.error(f"Error fetching prices: {e}")
            return {}

    def get_market_context(self, tickers):
        """
        獲取更詳細的市場數據 (用於 Agent Context)
        包含價格與技術指標
        """
        context = {}
        prices = self.get_current_prices(tickers)
        
        for ticker in tickers:
            price = prices.get(ticker)
            indicators = self.get_technical_indicators(ticker)
            
            # AI Fallback
            if price is None or price == 0:
                self.logger.warning(f"Missing data for {ticker}, attempting AI fallback...")
                ai_data = self._fetch_from_llm(ticker)
                if ai_data:
                    price = ai_data.get('price', 0)
                    if 'indicators' in ai_data:
                        indicators.update(ai_data['indicators'])
            
            context[ticker] = {
                "price": price,
                "indicators": indicators
            }
        return context

    def get_technical_indicators(self, ticker):
        """
        計算技術指標 (RSI, MACD)
        return: dict
        """
        try:
            df = yf.download(ticker, period="3mo", progress=False, auto_adjust=True)
            if df.empty or len(df) < 26: 
                return {"rsi": 50, "macd": "neutral"} 
            
            close = df['Close']
            if isinstance(close, pd.DataFrame):
                close = close.iloc[:, 0] 
            
            # RSI (14)
            delta = close.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            current_rsi = rsi.iloc[-1]
            
            # MACD (12, 26, 9)
            exp1 = close.ewm(span=12, adjust=False).mean()
            exp2 = close.ewm(span=26, adjust=False).mean()
            macd = exp1 - exp2
            signal = macd.ewm(span=9, adjust=False).mean()
            
            macd_val = macd.iloc[-1]
            signal_val = signal.iloc[-1]
            
            macd_status = "bullish" if macd_val > signal_val else "bearish"
            
            return {
                "rsi": round(float(current_rsi), 2) if pd.notna(current_rsi) else 50,
                "macd": macd_status,
                "macd_val": round(float(macd_val), 2) if pd.notna(macd_val) else 0
            }
            
        except Exception as e:
            self.logger.error(f"Error calculating indicators for {ticker}: {e}")
            return {"rsi": 50, "macd": "neutral"}

    def get_news(self, ticker):
        """
        獲取個股新聞
        return: list of str (Title - Link)
        """
        try:
            t = yf.Ticker(ticker)
            news = t.news
            if not news:
                return []
            
            formatted_news = []
            for n in news[:5]: # 取前 5 則
                title = n.get('title', '')
                link = n.get('link', '')
                pubDate = n.get('providerPublishTime', '') # Timestamp
                formatted_news.append(f"{title} ({link})")
            return formatted_news
        except Exception as e:
            self.logger.error(f"Error fetching news for {ticker}: {e}")
            return []

    def get_financials(self, ticker):
        """
        獲取基本面數據
        return: dict
        """
        try:
            t = yf.Ticker(ticker)
            info = t.info
            
            return {
                "market_cap": info.get('marketCap'),
                "trailing_pe": info.get('trailingPE'),
                "forward_pe": info.get('forwardPE'),
                "eps": info.get('trailingEps'),
                "revenue_growth": info.get('revenueGrowth'),
                "profit_margins": info.get('profitMargins'),
                "sector": info.get('sector'),
                "industry": info.get('industry')
            }
        except Exception as e:
            self.logger.error(f"Error fetching financials for {ticker}: {e}")
            return {}

    def get_macro_data(self):
        """
        獲取總經數據 (VIX, 10Y Yield, SPY)
        return: dict
        """
        try:
            tickers = ["^VIX", "^TNX", "SPY"]
            data = yf.download(tickers, period="5d", progress=False, auto_adjust=True)
            
            result = {}
            if not data.empty and 'Close' in data.columns:
                close = data['Close']
                # Handle MultiIndex columns if necessary (yf v0.2+)
                for t in tickers:
                    try:
                        val = close[t].iloc[-1]
                        if pd.notna(val):
                            result[t] = round(float(val), 2)
                    except KeyError:
                        pass
            return result
        except Exception as e:
            self.logger.error(f"Error fetching macro data: {e}")
            return {}

    def _fetch_from_llm(self, ticker):
        """
        使用 LLM 查詢市場資訊 (Fallback)
        """
        try:
            import requests
            import json
            
            conn = get_db_connection()
            # conn is now engine.connect()
            # fetchall() works on ResultProxy in 1.4+
            settings_rows = conn.execute(text("SELECT key, value FROM settings")).fetchall()
            settings = dict(settings_rows)
            conn.close()
            
            provider = settings.get("AI_PROVIDER")
            api_key = settings.get("API_KEY")
            model = settings.get("AI_MODEL")
            base_url = settings.get("BASE_URL")
            
            if not api_key:
                return None
                
            prompt = f"What is the current stock price of {ticker}? Please provide a rough estimate based on your knowledge. Return ONLY a JSON string like {{\"price\": 150.0, \"indicators\": {{\"rsi\": 50, \"macd\": \"neutral\"}}}}."
            
            content = ""
            if provider == "OpenRouter":
                resp = requests.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={"model": model, "messages": [{"role": "user", "content": prompt}]}
                )
                if resp.status_code == 200:
                    content = resp.json()['choices'][0]['message']['content']
            elif provider == "Google Gemini":
                model_id = model if model.startswith("models/") else f"models/{model}"
                resp = requests.post(
                    f"https://generativelanguage.googleapis.com/v1beta/{model_id}:generateContent?key={api_key}",
                    headers={"Content-Type": "application/json"},
                    json={"contents": [{"parts": [{"text": prompt}]}]}
                )
                if resp.status_code == 200:
                    content = resp.json()['candidates'][0]['content']['parts'][0]['text']
            
            if content:
                content = content.replace("```json", "").replace("```", "").strip()
                return json.loads(content)
                
        except Exception as e:
            self.logger.error(f"LLM fallback failed: {e}")
            return None
