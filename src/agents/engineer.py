import json
from datetime import datetime
import difflib
import os
import uuid
import re
from sqlalchemy import text
from src.agents.base_agent import BaseAgent
from src.utils.time_utils import format_time
from src.repositories.prompt_repository import AlchemyPromptRepository

class SystemEngineerAgent(BaseAgent):
    def __init__(self, use_cache=False, prompt_repo=None, **kwargs):
        # Engineer Agent usually does not cache because feedback varies every time.
        # Engineer Agent 通常不快取，因為每次回饋都不同。
        super().__init__(name="Engineer", prompt_path="prompts/engineer_agent.txt", use_cache=use_cache, tier="smart", **kwargs)
        self.prompt_repo = prompt_repo or AlchemyPromptRepository()

    def analyze_optimization_needs(self, cio_report):
        """
        Parse CIO report to identify 'System Optimization Feedback'.
        解析 CIO 報告，找出 'System Optimization Feedback'。
        
        Returns: list of dict [{'target': 'Momentum', 'reason': '...'}]
        回傳: list of dict [{'target': 'Momentum', 'reason': '...'}]
        
        (Currently simplified to handle only one main feedback item, or parsed by LLM)
        (目前簡化為只處理一個主要回饋，或由 LLM 解析)
        """
        # Simple string parsing to extract the section
        # 簡單的文字解析，抓取章節
        feedback_section = ""
        if "System Optimization Feedback" in cio_report:
            parts = cio_report.split("System Optimization Feedback")
            if len(parts) > 1:
                feedback_section = parts[1].strip()

        if not feedback_section or "無" in feedback_section or "None" in feedback_section:
            # Check for HR Request (New in Stage 5)
            if "[HR_REQUEST]" in cio_report:
                import re
                match = re.search(r"\[HR_REQUEST\] Replace Agent: (\w+) \(Reason: ([^)]*)\)", cio_report)
                if match:
                    agent_name = match.group(1)
                    reason = match.group(2)
                    return [{"raw_feedback": f"HR Inactivity Trigger: {reason}", "target_agent": agent_name}]
            return []

        # Here we could call LLM again to structurally parse the Feedback,
        # 這裡其實可以再呼叫一次 LLM 來結構化解析 Feedback，
        
        # but to save costs, we use simple rules or pass the entire feedback to `run` for processing.
        # 但為了節省成本，我們先用簡單規則，或者直接把這段 feedback 丟給 run 去處理。
        
        # Assuming we handle end-to-end service in `run`: parse -> optimize.
        # 假設我們在 run 裡面做完整的一條龍服務：解析 -> 優化。
        return [{"raw_feedback": feedback_section}]

    def _read_prompt(self, prompt_path):
        if not os.path.exists(prompt_path):
            return ""
        with open(prompt_path, "r") as f:
            return f.read()

    def _redact_secrets(self, text_value):
        """
        Best-effort redaction of common secret patterns (API keys, bearer tokens)
        before persisting content to disk.
        """
        if not isinstance(text_value, str):
            return text_value

        redacted = text_value

        # Redact obvious bearer tokens (e.g., "Authorization: Bearer <token>" or "Bearer <token>")
        redacted = re.sub(
            r"(Authorization:\s*Bearer\s+)[^\s\"']+",
            r"\1[REDACTED]",
            redacted,
            flags=re.IGNORECASE,
        )
        redacted = re.sub(
            r"(Bearer\s+)[^\s\"']+",
            r"\1[REDACTED]",
            redacted,
            flags=re.IGNORECASE,
        )

        # Redact common api_key patterns in code / JSON / config-like text
        redacted = re.sub(
            r"([\"']?api_key[\"']?\s*[:=]\s*[\"'])[A-Za-z0-9_\-\.]+([\"'])",
            r"\1[REDACTED]\2",
            redacted,
            flags=re.IGNORECASE,
        )
        redacted = re.sub(
            r"([\"']?API_KEY[\"']?\s*[:=]\s*[\"'])[A-Za-z0-9_\-\.]+([\"'])",
            r"\1[REDACTED]\2",
            redacted,
            flags=re.IGNORECASE,
        )

        return redacted

    def _save_prompt(self, prompt_path, file_content):
        # Redact any accidental secrets before writing to disk to avoid CodeQL false positive heuristics
        safe_content = self._redact_secrets(file_content)
        with open(prompt_path, "w") as f:
            f.write(safe_content)

    def _log_prompt_change(self, agent_name, reason, old_prompt, new_prompt, diff):
        try:
            self.prompt_repo.log_change(agent_name, reason, old_prompt, new_prompt, diff, user_id=self.user_id)
        except Exception as e:
            self.logger.error(f"Error logging prompt change: {e}")

    def run(self, context):
        """
        context: {
            "cio_report": "...",
            "target_agent_name": "Momentum" (Optional, if we want to force optimize specific agent)
        }
        """
        cio_report = context.get("cio_report", "")

        # 1. Get Feedback
        # 1. 取得 Feedback
        optimizations = self.analyze_optimization_needs(cio_report)
        if not optimizations:
            return []

        results = []

        # 2. Optimize for each requirement (Currently simplified logic, assuming Feedback contains target name)
        # 2. 針對每一條需求進行優化 (目前簡化邏輯，假設 Feedback 包含對象名稱)
        
        # For demonstration, assume CIO feedback text mentions 'Momentum'
        # 為了展示，我們假設 CIO 裡面的 Feedback 文字有提到 'Momentum'
        raw_feedback = optimizations[0]['raw_feedback']

        target_agent = "Momentum" # Default or detected
        
        # New Workspace mappings
        workspace_map = {
            "Momentum": "market-scanner",
            "Fundamental": "data-prep",
            "Macro": "macro-evaluator",
            "CIO": "captain",
            "Risk": "risk-assessor",
            "Sentiment": "sentiment-analyst",
            "Thematic": "portfolio-manager"
        }

        if "Fundamental" in raw_feedback:
            target_agent = "Fundamental"
        elif "Macro" in raw_feedback:
            target_agent = "Macro"
        elif "CIO" in raw_feedback or "Captain" in raw_feedback:
            target_agent = "CIO"
        elif "Risk" in raw_feedback:
            target_agent = "Risk"
        elif "Sentiment" in raw_feedback:
            target_agent = "Sentiment"
        elif "Thematic" in raw_feedback:
            target_agent = "Thematic"

        # Determine target path
        ws_name = workspace_map.get(target_agent, target_agent.lower().replace(" ", "-"))
        workspace_dir = f"workspace/{ws_name}"
        target_path = f"{workspace_dir}/IDENTITY.md"

        # Fallback to legacy path if workspace does not exist or IDENTITY.md doesn't exist
        if not os.path.exists(target_path):
            legacy_map = {
                "Momentum": "prompts/momentum_agent.txt",
                "Fundamental": "prompts/fundamental_agent.txt",
                "Macro": "prompts/macro_agent.txt",
                "CIO": "prompts/cio_weekly.txt",
                "Risk": "prompts/risk_agent.txt",
                "Sentiment": "prompts/sentiment_agent.txt",
                "Thematic": "prompts/thematic_agent.txt"
            }
            target_path = legacy_map.get(target_agent, f"prompts/{target_agent.lower()}_agent.txt")

        original_prompt = self._read_prompt(target_path)

        # 3. Construct Prompt for Engineer LLM
        # 3. 組建 Prompt 給 Engineer LLM
        engineer_input = {
            "cio_feedback": raw_feedback,
            "target_agent_prompt": original_prompt
        }

        sys_prompt = self.system_prompt
        user_prompt = json.dumps(engineer_input, ensure_ascii=False)

        # 4. Call LLM
        # 4. 呼叫 LLM
        response_str = self._call_real_llm(user_prompt, sys_prompt)

        # Parse JSON output (Need to handle potential Markdown code block)
        # 解析 JSON 輸出 (需處理可能 Markdown code block)
        try:
            cleaned_response = response_str.replace("```json", "").replace("```", "").strip()
            result_json = json.loads(cleaned_response)

            new_prompt = result_json.get("optimized_prompt", "")
            diff_explanation = result_json.get("diff_explanation", "")

            if new_prompt and new_prompt != original_prompt:
                # Generate Diff
                # 產生 Diff
                diff = difflib.unified_diff(
                    original_prompt.splitlines(),
                    new_prompt.splitlines(),
                    lineterm=""
                )
                diff_text = "\n".join(list(diff))

                # Save file
                # 存檔
                self._save_prompt(target_path, new_prompt)

                # Write to DB
                # 寫入 DB
                self._log_prompt_change(target_agent, raw_feedback, original_prompt, new_prompt, diff_text)

                results.append({
                    "target_agent": target_agent,
                    "reason": raw_feedback,
                    "goal": "Performance Optimization",
                    "before_snippet": original_prompt[:200] + "...",
                    "after_snippet": new_prompt[:200] + "...",
                    "diff": diff_text
                })
            else:
                results.append({
                    "target_agent": target_agent,
                    "reason": "No optimization needed or possible",
                    "goal": "N/A",
                    "diff": None
                })

        except json.JSONDecodeError:
            results.append({"error": f"Failed to parse Engineer Agent response for {target_agent}."})
        except Exception as e:
            results.append({"error": f"Error optimizing {target_agent}: {str(e)}"})

        return results # Return structured list


    # Dictionary-like access methods for schedule config (Phase 37)
    def get_schedule_config(self):
        """
        Read schedule config from database (Via Settings Repo).
        從資料庫讀取排程設定 (Via Settings Repo)。
        """
        config = {}
        try:
            # key, value tuples or dict?
            # Repo returns rows: [(key, val), ...]
            rows = self.settings_repo.get_by_prefix("schedule_")
            for row in rows:
                key = row._mapping['key'] if hasattr(row, '_mapping') else row[0]
                val = row._mapping['value'] if hasattr(row, '_mapping') else row[1]
                config[key] = val
        except Exception as e:
            self.logger.error(f"Error reading schedule config: {e}")
        
        return config

    def set_schedule_config(self, daily_time, weekly_time, weekly_day="saturday", daily_days=None):
        """
        Update schedule config (Via Settings Repo).
        更新排程設定 (Via Settings Repo)。
        """
        try:
            updates = {
                "schedule_daily": daily_time,
                "schedule_weekly": weekly_time,
                "schedule_weekly_day": weekly_day
            }
            
            if daily_days is not None:
                # Serialize list to CSV string
                if isinstance(daily_days, list):
                    updates["schedule_daily_days"] = ",".join(daily_days)
                else:
                    updates["schedule_daily_days"] = str(daily_days)

            for key, value in updates.items():
                # Use user_id context or system default?
                # Assuming schedule is global, use self.user_id which defaults to "system"
                self.settings_repo.set(self.user_id, key, value)

            self.logger.info("Schedule config updated via Engineer Agent.")
        except Exception as e:
            self.logger.error(f"Error updating schedule config: {e}")
