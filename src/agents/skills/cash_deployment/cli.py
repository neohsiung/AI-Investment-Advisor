import sys
import argparse
import os
import asyncio

# Add project root to sys.path
sys.path.append(os.getcwd())

from src.utils.logger import setup_logger
from src.agents.skills.cash_deployment.impl import (
    BrokerFactory,
    AlchemySettingsRepository,
    cash_deployment,
    _get_deployment_candidates,
)

logger = setup_logger("cash_deployment_cli")


async def main():
    parser = argparse.ArgumentParser(description="Analyze and suggest deployment for excess cash.")
    parser.add_argument("--user_id", required=True, help="User ID context")
    args = parser.parse_args()

    result = await cash_deployment(args.user_id)
    print(result)


if __name__ == "__main__":
    asyncio.run(main())

