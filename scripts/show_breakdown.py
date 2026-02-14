import os
import sys
import pandas as pd
from dotenv import load_dotenv

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.services.dashboard_service import DashboardService
from src.services.etoro_service import EtoroService
from src.repositories.settings_repository import SqliteSettingsRepository

def main():
    load_dotenv()
    user_id = "supermfb@gmail.com"
    
    ds = DashboardService()
    
    print("Fetching Dashboard Data...")
    data = ds.prepare_dashboard_data(user_id)
    
    # Extract
    metrics = data['metrics']
    positions_df = data['positions_df']
    cash = metrics['cash_balance']
    
    print(f"\n{'TICKER':<6} | {'QTY':<8} | {'PRICE':<8} | {'LEV':<3} | {'GROSS MV':<10} | {'LOAN':<8} | {'NET EQ':<10}")
    print("-" * 75)
    
    total_gross = metrics.get('gross_nlv', 0.0) - cash
    total_net = metrics.get('nlv', 0.0) - cash
    
    if not positions_df.empty:
        for _, row in positions_df.iterrows():
            tkr = row['ticker']
            qty = row['quantity']
            px = row['current_price']
            lev = row['leverage']
            gross = row['gross_mv']
            loan = row['loan']
            net_eq = row['net_equity']
            
            print(f"{tkr:<6} | {qty:<8.4f} | {px:<8.2f} | {lev:<3.1f} | {gross:<10.2f} | {loan:<8.2f} | {net_eq:<10.2f}")
    else:
        print("No positions found.")
        
    print("-" * 75)
    print(f"{'SUM POSITIONS':<39} | {total_gross:<10.2f} | {sum(positions_df['loan']):<8.2f} | {total_net:<10.2f}")
    print(f"CASH: ${cash:.2f}")
    print(f"\nTOTAL NLV (Gross + Cash): ${metrics.get('gross_nlv', 0):.2f}")
    print(f"TOTAL NLV (Net + Cash):   ${metrics.get('nlv', 0):.2f}")
    print(f"Leverage Ratio (Financial): {metrics.get('leverage_ratio', 0):.2f}x")
    
    print("\n[Summary for User]")
    print(f"Final Calculated NLV (Net Equity + Cash): ${total_net + cash:.2f}")
    print(f"User Expectation:                        $1182.15")

if __name__ == "__main__":
    main()
