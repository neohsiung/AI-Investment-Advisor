from fastapi import APIRouter, Depends, HTTPException, Request, Body
from fastapi.responses import StreamingResponse
from typing import Dict, Any, List
import json
import asyncio
import re

from src.api.v1.router import get_current_user_id
from src.agents.factory import AgentFactory
from src.utils.logger import setup_logger

logger = setup_logger("API_Chat")
router = APIRouter()

@router.post("")
async def advisor_chat(
    payload: Dict[str, Any] = Body(...),
    user_id: str = Depends(get_current_user_id)
):
    """AI 投資顧問對話介面 (即時諮詢模式)"""
    try:
        prompt = payload.get("message", "")
        history = payload.get("history", [])

        if not prompt:
            raise HTTPException(status_code=400, detail="Message is required")

        factory = AgentFactory()
        cio_agent = factory.create_cio_agent(user_id=user_id)

        system_prompt = (
            "You are a professional AI Investment Advisor. "
            "Your goal is to answer the user's financial questions concisely, directly, and interactively. "
            "Use traditional Chinese (繁體中文)."
        )
        messages = [{"role": "system", "content": system_prompt}]
        for msg in history[-10:]:
            messages.append(msg)
        messages.append({"role": "user", "content": prompt})

        # Phase 12: agents are async-native
        response = await cio_agent.call_llm(messages=messages, temperature=0.7)

        return {
            "status": "success",
            "data": {
                "message": response
            }
        }
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/stream")
async def advisor_chat_stream(
    payload: Dict[str, Any] = Body(...),
    user_id: str = Depends(get_current_user_id)
):
    """AI 投資顧問對話介面 (串流模式)"""
    try:
        prompt = payload.get("message", "")
        history = payload.get("history", [])

        if not prompt:
            raise HTTPException(status_code=400, detail="Message is required")

        factory = AgentFactory()
        cio_agent = factory.create_cio_agent(user_id=user_id)

        async def event_generator():
            try:
                from src.repositories.pulse_repository import AsyncPulseRepository
                pulse_repo = AsyncPulseRepository()
                
                prompt_data = {
                    "user_id": user_id,
                    "task_instruction": prompt,
                    "topic": "General",
                }
                
                await pulse_repo.update_pulse(cio_agent.name, "Initializing Agent...")
                
                # Run the Agent loop
                task = asyncio.create_task(cio_agent.run_tool_loop(
                    context=prompt_data, 
                    max_turns=3, 
                    thought_chain=True
                ))
                
                last_task_state = None
                while not task.done():
                    current_pulse = await pulse_repo.get_pulse(cio_agent.name)
                    if current_pulse:
                        current_state = current_pulse.get("task")
                        if current_state and current_state != last_task_state:
                            yield f"data: {json.dumps({'metadata': {'type': 'tool_call', 'name': current_state}})}\n\n"
                            last_task_state = current_state
                    await asyncio.sleep(0.5)
                
                final_response = await task
                
                # Simulated streaming of the result
                chunks = re.findall(r'\S+|\n|\s+', final_response)
                for c in chunks:
                    yield f"data: {json.dumps({'chunk': c})}\n\n"
                    await asyncio.sleep(0.01)
                    
                yield "data: [DONE]\n\n"
            except Exception as e:
                logger.error(f"Streaming error: {e}")
                yield f"data: {json.dumps({'error': str(e)})}\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    except Exception as e:
        logger.error(f"Stream Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
