import json
import asyncio
from src.services.dashboard_service import DashboardService

async def main():
    try:
        # User ID from earlier psql query
        user_id = '90693c07-6177-42df-97d9-915f3ce7c573' 
        svc = DashboardService(user_id=user_id)
        
        # Await if 'prepare_dashboard_data' is async, else call sync
        if asyncio.iscoroutinefunction(svc.prepare_dashboard_data):
            data = await svc.prepare_dashboard_data(user_id=user_id)
        else:
            data = svc.prepare_dashboard_data(user_id=user_id)
            
        print("== Metrics from Dashboard Service ==")
        metrics = data.get('metrics', {})
        print(json.dumps(metrics, indent=2))
        
        print("\n== Net Invested Capital Check ==")
        print(f"Invested Capital: {metrics.get('invested_capital')}")
        
    except Exception as e:
        print("Error details:", str(e))
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
