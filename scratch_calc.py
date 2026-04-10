import yfinance as yf

positions = {
    'META': (0.411705, 5),
    'GOOG': (0.20593, 1),
    'COST': (0.020576, 1),
    'TSM': (0.48855507, 1),
    'VTI': (0.39611194, 1),
    'TSLA': (0.14168403, 1),
    'JPM': (0.074607, 1),
    'DDOG': (0.365764, 1),
    'GS': (0.110403, 2),
}

tickers = list(positions.keys())
data = yf.download(tickers, period='1d', progress=False)
prices = data['Close'].iloc[-1].to_dict() if not data.empty else {}

eq = 0
for t, (qty, lev) in positions.items():
    p = prices.get(t, 0)
    # Wait, the DB leverages the gross. If you have 0.411 shares of META and price is 500
    # Gross value is 0.411 * 500 = 205.
    # What is the equity? Equity = margin + unrl_pnl.
    # Or Equity = Gross - Loan. 
    # What is the Loan? Loan = (Avg Cost * Qty) - (Avg Cost * Qty / Lev).
    # This requires Avg Cost!
    pass
print("Prices:", prices)
