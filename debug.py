import asyncio
from src.services.dashboard_service import DashboardService

# Since we are outside the Docker container, tell get_db_engine to use localhost
import os
os.environ["DB_HOST"] = "localhost"

async def main():
    service = DashboardService(user_id="test_user")
    print("DashboardService created!")
    try:
        data = service.prepare_dashboard_data("test_user")
        print("Data prepared successfully.")
    except Exception as e:
        print("Exception:", str(e))
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
