from src.utils.logger import setup_logger

logger = setup_logger("skill_event_research")

async def event_research(
    user_id: str,
    ticker: str,
    event_source: str = "news",
    event_text: str = "",
    council_summary: str = "",
) -> str:
    """
    Event Research Skill — 針對新聞/事件觸發，執行 EventAnalysisWorkflow。
    可被 SentinelService、ConversationAgent、SchedulerAgent 調用。
    
    Args:
        user_id: 用戶 ID
        ticker: 目標標的（如 "MU", "NVDA"）
        event_source: 事件來源（"news", "earnings", "macro"）
        event_text: 原始觸發文字
        council_summary: Sentinel Council 的摘要（可選）
    
    Returns:
        研究結果摘要 (str)
    """
    try:
        from src.services.workflow_service import EventAnalysisWorkflow
        wf = EventAnalysisWorkflow(
            user_id=user_id,
            ticker=ticker,
            event_source=event_source,
            event_data={
                'msg': event_text,
                'council_summary': council_summary,
            },
            target_action='RESEARCH',
        )
        result = await wf.synthesize_results()
        logger.info(f"Event Research: Task completed for ticker={ticker}")
        return f"Research completed for {ticker}. Result: {str(result)[:200]}..."
    except Exception as e:
        logger.warning(f"Event Research: Task failed for ticker={ticker}: {e}")
        return f"Failed to complete research for {ticker}: {e}"
