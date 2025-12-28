import os
import sys

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.services.workflow_service import DailyWorkflow
from src.repositories.transaction_repository import SqliteTransactionRepository

def generate_report():
    print("Initializing Report Generation...")
    user_id = "admin@example.com"
    
    # 1. Ensure user has data to trigger report
    repo = SqliteTransactionRepository()
    tickers = repo.get_unique_tickers(user_id)
    if not tickers:
        print(f"Seeding dummy transaction for {user_id}...")
        try:
             # Use direct connection if add method sig varies or just use add
             # add(user_id, ticker, date, action, qty, price, fees)
             repo.add(user_id, "AAPL", "2025-01-01", "BUY", 10.0, 150.0, 0.0)
        except Exception as e:
            print(f"Error seeding data: {e}")
            # Fallback to manual insert or proceed hoping for best
            pass

    # 2. Run Workflow
    svc = DailyWorkflow(user_id=user_id)
    print(f"Running Daily Workflow for {user_id}...")
    
    try:
        result = svc.run(dry_run=True, force_refresh=True)
    except Exception as e:
        print(f"Workflow execution failed: {e}")
        result = f"Error: {e}"

    # 3. Handle Result
    report_content = ""
    if result == "SKIPPED":
        report_content = "Workflow SKIPPED. No tickers or market closed."
        print(report_content)
    else:
        report_content = str(result)
        print("Workflow Completed.")

    # 4. Save to file
    output_path = "reports/verification_report.md"
    os.makedirs("reports", exist_ok=True)
    with open(output_path, "w") as f:
        f.write(report_content)
        
    print(f"Report saved to {output_path}")

if __name__ == "__main__":
    generate_report()
