"""
Reflection Prompt Template — Phase 6.
反思與自動容錯提示詞模板。

Used when a tool/skill execution fails to allow the agent to self-correct.
當工具執行失敗時，提供給 Agent 進行自我修正的提示詞背景。
"""

from typing import Dict, Any

class ReflectionPrompt:
    """
    Template for tool-usage reflection.
    """
    VERSION = "1.0.0"
    
    @staticmethod
    def build(tool_name: str, tool_args: Any, error_message: str) -> str:
        return f"""
# Task: Self-Correction (Auto-Reflection)
# 任務：自我修復（自動反思）

## Context
You are an expert financial advisor agent. You recently attempted to execute a tool (skill), but it failed with an error.
你是一位專業的金融顧問 Agent。你剛剛嘗試執行一個工具（技能），但發生了錯誤。

## Tool Execution Failure Details
- **Tool Name**: {tool_name}
- **Input Arguments**: {tool_args}
- **Error/Traceback**: 
{error_message}

## Analysis Requirements
Please analyze the failure and provide a corrected course of action:
1. **Root Cause**: Why did it fail? (e.g. invalid date format, missing required parameter, symbol not found)
2. **Corrected Input**: Provide a valid JSON string for the parameters that you believe will work.
3. **Recommended Action**: Decide if we should "retry" with corrected args, "fail" if it's unfixable, or "alternative" if another tool is better.

## Output Format
Return your analysis in a structured JSON format:
{{
  "analysis": "Brief explanation of the root cause",
  "recommended_action": "retry" | "fail" | "alternative",
  "corrected_args": {{ ... }},
  "alternative_tool": "name_of_tool_if_applicable"
}}

Respond ONLY with the JSON object.
""".strip()

    @staticmethod
    def build_compressed(tool_name: str, tool_args: Any, error_message: str) -> str:
        """
        Compressed version for emergency budget scenarios.
        """
        return f"""
FAIL: {tool_name}({tool_args}) -> {error_message}
FIX: analyze error, output JSON ONLY: 
{{"analysis": "str", "recommended_action": "retry|fail|alternative", "corrected_args": {{}}, "alternative_tool": "opt"}}
""".strip()
