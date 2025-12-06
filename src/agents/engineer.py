import json
from datetime import datetime
import difflib
import os
import uuid
from sqlalchemy import text
from src.agents.base_agent import BaseAgent
from src.database import get_db_connection
from src.utils.time_utils import format_time

class SystemEngineerAgent(BaseAgent):
    def __init__(self, use_cache=False):
        # Engineer Agent 通常不快取，因為每次回饋都不同
        super().__init__(name="Engineer", prompt_path="prompts/engineer_agent.txt", use_cache=use_cache)

    def analyze_optimization_needs(self, cio_report):
        """
        解析 CIO 報告，找出 'System Optimization Feedback'
        回傳: list of dict [{'target': 'Momentum', 'reason': '...'}]
        (目前簡化為只處理一個主要回饋，或由 LLM 解析)
        """
        # 簡單的文字解析，抓取章節
        feedback_section = ""
        if "System Optimization Feedback" in cio_report:
            parts = cio_report.split("System Optimization Feedback")
            if len(parts) > 1:
                feedback_section = parts[1].strip()
        
        if not feedback_section or "無" in feedback_section or "None" in feedback_section:
            return []

        # 這裡其實可以再呼叫一次 LLM 來結構化解析 Feedback，
        # 但為了節省成本，我們先用簡單規則，或者直接把這段 feedback 丟給 run 去處理
        # 假設我們在 run 裡面做完整的一條龍服務：解析 -> 優化
        return [{"raw_feedback": feedback_section}]

    def _read_prompt(self, prompt_path):
        if not os.path.exists(prompt_path):
            return ""
        with open(prompt_path, "r") as f:
            return f.read()

    def _save_prompt(self, prompt_path, content):
        with open(prompt_path, "w") as f:
            f.write(content)

    def _log_prompt_change(self, agent_name, reason, old_prompt, new_prompt, diff):
        conn = get_db_connection()
        try:
            log_id = str(uuid.uuid4())
            timestamp = datetime.now().isoformat()
            
            conn.execute(text('''
                INSERT INTO prompt_history (id, timestamp, target_agent, reason, original_prompt, new_prompt, diff_content)
                VALUES (:id, :timestamp, :target_agent, :reason, :original_prompt, :new_prompt, :diff_content)
            '''), {
                "id": log_id,
                "timestamp": timestamp,
                "target_agent": agent_name,
                "reason": reason,
                "original_prompt": old_prompt,
                "new_prompt": new_prompt,
                "diff_content": diff
            })
            conn.commit()
        except Exception as e:
            self.logger.error(f"Error logging prompt change: {e}")
        finally:
            conn.close()

    def run(self, context):
        """
        context: {
            "cio_report": "...",
            "target_agent_name": "Momentum" (Optional, if we want to force optimize specific agent)
        }
        """
        cio_report = context.get("cio_report", "")
        
        # 1. 取得 Feedback
        optimizations = self.analyze_optimization_needs(cio_report)
        if not optimizations:
            return "No optimization feedback found."

        results = []
        
        # 2. 針對每一條需求進行優化 (目前簡化邏輯，假設 Feedback 包含對象名稱)
        # 為了展示，我們假設 CIO 裡面的 Feedback 文字有提到 'Momentum'
        raw_feedback = optimizations[0]['raw_feedback']
        
        target_agent = "Momentum" # Default or detected
        target_path = "prompts/momentum_agent.txt"
        
        if "Fundamental" in raw_feedback:
            target_agent = "Fundamental"
            target_path = "prompts/fundamental_agent.txt"
        elif "Macro" in raw_feedback:
            target_agent = "Macro"
            target_path = "prompts/macro_agent.txt"
            
        original_prompt = self._read_prompt(target_path)
        
        # 3. 組建 Prompt 給 Engineer LLM
        engineer_input = {
            "cio_feedback": raw_feedback,
            "target_agent_prompt": original_prompt
        }
        
        sys_prompt = self.system_prompt
        user_prompt = json.dumps(engineer_input, ensure_ascii=False)
        
        # 4. 呼叫 LLM
        response_str = self._call_real_llm(user_prompt, sys_prompt)
        
        # 解析 JSON 輸出 (需處理可能 Markdown code block)
        try:
            cleaned_response = response_str.replace("```json", "").replace("```", "").strip()
            result_json = json.loads(cleaned_response)
            
            new_prompt = result_json.get("optimized_prompt", "")
            diff_explanation = result_json.get("diff_explanation", "")
            
            if new_prompt and new_prompt != original_prompt:
                # 產生 Diff
                diff = difflib.unified_diff(
                    original_prompt.splitlines(),
                    new_prompt.splitlines(),
                    lineterm=""
                )
                diff_text = "\n".join(list(diff))
                
                # 存檔
                self._save_prompt(target_path, new_prompt)
                
                # 寫入 DB
                self._log_history(target_agent, raw_feedback, original_prompt, new_prompt, diff_text)
                
                results.append(f"Optimized {target_agent}: {diff_explanation}")
            else:
                results.append(f"No changes made to {target_agent}.")
                
        except json.JSONDecodeError:
            results.append(f"Failed to parse Engineer Agent response for {target_agent}.")
        except Exception as e:
            results.append(f"Error optimizing {target_agent}: {e}")

        return "\n".join(results)

    # Dictionary-like access methods for schedule config (Phase 37)
    def get_schedule_config(self):
        """從資料庫讀取排程設定"""
        conn = get_db_connection()
        config = {}
        try:
            rows = conn.execute(text("SELECT key, value FROM settings WHERE key LIKE 'schedule_%'")).fetchall()
            for row in rows:
                # row access
                key = row[0] # or row._mapping['key']
                val = row[1]
                config[key] = val
        except Exception as e:
            self.logger.error(f"Error reading schedule config: {e}")
        finally:
            conn.close()
            
        return config

    def set_schedule_config(self, daily_time, weekly_time):
        """更新排程設定"""
        conn = get_db_connection()
        try:
            updates = {
                "schedule_daily": daily_time,
                "schedule_weekly": weekly_time
            }
            
            for key, value in updates.items():
                conn.execute(text("INSERT OR REPLACE INTO settings (key, value) VALUES (:key, :value)"), {"key": key, "value": value})
            
            conn.commit()
            self.logger.info("Schedule config updated via Engineer Agent.")
        except Exception as e:
            self.logger.error(f"Error updating schedule config: {e}")
        finally:
            conn.close()
