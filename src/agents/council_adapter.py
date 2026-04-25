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

    async def run(self, context: dict) -> dict:
        """
        Asynchronous run method for CouncilAgentAdapter.
        CouncilAgentAdapter 的非同步執行方法。
        """
        user_id = context.get("user_id") or self.user_id
        if not user_id:
             raise ValueError("CouncilAgentAdapter: No user_id provided in context or init.")
        
        return await self.service.start_session(
            topic=self.topic, 
            context_data=context, 
            user_id=user_id, 
            scope=self.scope
        )
