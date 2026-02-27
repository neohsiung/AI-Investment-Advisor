import asyncio
import os
from dotenv import load_dotenv
from src.data.database import get_db_engine
from src.repositories.transaction_repository import AlchemyTransactionRepository
from src.services.analytics_service import PnLCalculator

def main():
    load_dotenv()
    os.environ['DB_HOST'] = 'localhost'
    user_id = '90693c07-6177-42df-97d9-915f3ce7c573'

    engine = get_db_engine()
    repo = AlchemyTransactionRepository(engine)
    pnl_calc = PnLCalculator(repository=repo)
    
    # 1. DB Breakdown
    print("=== DB PORTFOLIO (qty, avg_cost, margin_invested) ===")
    
    # Let's see actual DB details
    prices_zero = {t: 0.0 for t in repo.get_active_tickers(user_id)}
    pnl = pnl_calc.calculate_breakdown(prices_zero, user_id)
    
    total_db_margin = 0
    total_db_invested = 0
    for t, p in pnl['details'].items():
        if p['qty'] > 0:
            inv = p['qty'] * p['avg_cost']
            marg = p.get('margin_invested', 0)
            total_db_margin += marg
            total_db_invested += inv
            print(f"{t}: qty={p['qty']:.6f}, cost={p['avg_cost']:.2f}, margin={marg:.2f} (nom: {inv:.2f})")
    
    print(f"Total DB Nominal Invested: {total_db_invested:.2f}")
    print(f"Total DB Margin Invested: {total_db_margin:.2f}")
    print(f"DB Cash Balance: {repo.get_cash_balance(user_id):.2f}\n")
    
    # 2. eToro Breakdown (Live API)
    print("=== ETORO PORTFOLIO (Live) ===")
    from src.services.etoro_service import EtoroService
    etoro = EtoroService(user_id=user_id) # Fix positional arg
    
    account = etoro.get_account()
    if account:
        print(f"eToro Total Equity: {account.total_equity}")
        print(f"eToro Total Cash: {account.available_cash}")
    
    positions = etoro.get_positions()
    total_etoro_val = 0
    total_etoro_unrealized = 0
    
    for p in positions:
        print(f"{p.symbol}: qty={p.quantity:.6f}, val={p.market_value:.2f}, unrealized={p.unrealized_pnl:.2f}, price={p.current_price:.2f}, leverage={p.leverage}")
        total_etoro_val += p.market_value
        total_etoro_unrealized += p.unrealized_pnl
        
    print(f"\nTotal eToro Market Value: {total_etoro_val:.2f}")
    print(f"Total eToro Unrealized PnL: {total_etoro_unrealized:.2f}")
    
    print("\n--- Summary of the Math ---")
    print(f"If we follow exactly: NLV = DB Cash ({repo.get_cash_balance(user_id):.2f}) + DB Invested ({total_db_invested:.2f}) + eToro Unrealized ({total_etoro_unrealized:.2f})")
    print(f"NLV Computed this way is: {repo.get_cash_balance(user_id) + total_db_invested + total_etoro_unrealized:.2f}")

if __name__ == "__main__":
    main()
