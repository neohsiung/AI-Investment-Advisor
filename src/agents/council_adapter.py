from src.services.council_service import CouncilService
import asyncio

class CouncilAgentAdapter:
    """
    Adapts the async CouncilService to the synchronous BaseAgent interface 
    expected by WeeklyWorkflow.
    將非同步的 CouncilService 適配為 WeeklyWorkflow 所期望的同步 BaseAgent 介面。
    """
    def __init__(self, user_id: str, scope="portfolio", topic="Portfolio Analysis"):
        self.user_id = user_id
        self.service = CouncilService(user_id=user_id)
        self.scope = scope
        self.topic = topic
        self.name = "Council Agent (Map-Reduce)"

    def run(self, context: dict) -> dict:
        """
        Synchronous wrapper for start_session.
        start_session 的同步封裝函式。
        """
        user_id = context.get("user_id") or self.user_id
        if not user_id:
             raise ValueError("CouncilAgentAdapter: No user_id provided in context or init.")
        
        # Create a new loop if needed, or use existing
        try:
             loop = asyncio.get_event_loop()
        except RuntimeError:
             loop = asyncio.new_event_loop()
             asyncio.set_event_loop(loop)
        
        if loop.is_running():
             # If we are already in an async context (unlikely for sync workflow but possible)
             # We might need a thread.
             import concurrent.futures
             with concurrent.futures.ThreadPoolExecutor() as executor:
                  future = executor.submit(asyncio.run, self.service.start_session(self.topic, context, user_id, self.scope))
                  return future.result()
        else:
             return loop.run_until_complete(self.service.start_session(self.topic, context, user_id, self.scope))
