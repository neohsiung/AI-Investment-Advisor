"""
Evolution Metrics Service — Cognitive Evolution Observability.
認知進化觀察性指標服務 [Phase 5C].

Tracks autonomous agent evolution events such as gap detections, 
scaffold successes/failures, and hot-reload events.

遵循規範:
  - 規範一 (Clean Architecture): Logging isolation.
  - 規範四 (模組化設計): Minimal dependencies.
"""
import logging
import json
import os
from datetime import datetime
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class EvolutionMetrics:
    """
    Logs and aggregates metrics related to agent self-evolution and skill scaffolding.
    """
    
    def __init__(self, log_path: str = "logs/evolution_metrics.jsonl"):
        self.log_path = log_path
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        
    def record_event(self, event_type: str, details: Dict[str, Any] = None) -> None:
        """
        Record a self-evolution lifecycle event.
        
        Common event types:
        - gap_detected
        - scaffolding_started
        - scaffolding_success
        - scaffolding_failed
        - skill_hot_reloaded
        - user_rejected_scaffold
        """
        payload = {
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": event_type,
            "details": details or {}
        }
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"EvolutionMetrics failed to record event: {e}")

    def record_reflection_event(self, tool_name: str, error_type: str, 
                               action: str, success: bool, 
                               duration_ms: int = 0) -> None:
        """
        Record a self-healing reflection event. [Phase 7]
        追踪代理自癒 (Self-Healing) 事件。
        """
        details = {
            "tool_name": tool_name,
            "error_type": error_type,
            "action": action,
            "success": success,
            "duration_ms": duration_ms
        }
        self.record_event("self_healing_reflection", details)
            
    def generate_report(self) -> str:
        """
        Produce a summary report of the agent's evolutionary activity.
        """
        if not os.path.exists(self.log_path):
            return "No evolution data available."
            
        counts: Dict[str, int] = {}
        total_events = 0
        try:
            with open(self.log_path, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        record = json.loads(line)
                        etype = record.get("event_type", "unknown")
                        counts[etype] = counts.get(etype, 0) + 1
                        total_events += 1
                    except json.JSONDecodeError:
                        continue
                        
            report = ["=== Phase 5C Cognitive Evolution Metrics ==="]
            report.append(f"Total Evolution Events: {total_events}")
            report.append("-" * 40)
            
            for evt, cnt in sorted(counts.items(), key=lambda x: str(x[0])):
                report.append(f"• {evt}: {cnt}")
            
            return "\n".join(report)
        except Exception as e:
            logger.error(f"Error generating evolution report: {e}")
            return f"Error generation report: {e}"
