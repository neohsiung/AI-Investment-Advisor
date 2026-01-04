import logging
import sys
import os
sys.path.append(os.getcwd())
from datetime import datetime
from src.agents.engineer import SystemEngineerAgent
from src.services.performance_service import PerformanceService
from src.notifier import EmailNotifier
from src.utils.logger import setup_logger

logger = setup_logger("MonthlyRefinement")

def main():
    logger.info("Starting Monthly Refinement (HR Protocol)...")
    
    try:
        # 1. Performance Review
        perf_service = PerformanceService()
        stats = perf_service.get_agent_performance()
        
        # 2. Engineer Analysis (HR View)
        engineer = SystemEngineerAgent(user_id="supermfb@gmail.com") # Hardcode or iterate users? Simplified for CLI task.
        # Ideally, scheduler calls this per user or global.
        # Since this is a system-wide refinement, we can treat it as global or per-user.
        # For verification, we target supermfb.
        
        # 3. Generate Evolution Report
        # We manually construct a prompt tasks for the Engineer to summarize system health
        hr_context = {
            "cio_report": "HR_PROTOCOL_INITIATED",
            "performance_stats": stats,
            "task": "Generate Monthly System Evolution Report"
        }
        
        # Engineer 'run' method expects 'cio_report'. 
        # But we want a generated report text.
        # Let's create a custom run or just inspect prompts.
        # Actually, let's just use the Engineer to "Analyze" and output a summary.
        # The Engineer.run returns optimization results (list).
        # We might need to ask the Engineer to write a report.
        # Let's use BaseAgent's _call_real_llm directly or just map results.
        
        # For this verification script, let's keep it simple:
        # Ask Engineer to 'check' prompts and logic.
        
        optimizations = engineer.run(hr_context)
        

        # Format stats into Markdown table

        # Format stats into Markdown table
        stats_md = "\n| Agent (分析師) | Win Rate (勝率) | Count (次數) | Status (狀態) |\n|---|---|---|---|\n"
        
        # Normalize and merge stats (case-insensitive)
        target_agents = ["CIO", "Momentum", "Fundamental", "Macro", "Sentiment"]
        
        merged_stats = {}
        # Initialize with defaults
        for agent in target_agents:
            merged_stats[agent] = {"wins": 0, "count": 0}

        if isinstance(stats, dict):
            for agent, data in stats.items():
                # Normalize key to Title Case
                norm_key = agent.title() 
                # Map specific variations if needed
                if norm_key.upper() == "CIO": norm_key = "CIO" # Keep CIO uppercase preference if desired, but "Cio" is fine too. Let's use Title case for all "Cio", "Macro" etc except "CIO" usually. 
                # Actually, let's standardize to the list above.
                
                # Flexible matching
                match_key = None
                for target in target_agents:
                    if target.lower() == agent.lower():
                        match_key = target
                        break
                
                if not match_key:
                    match_key = norm_key # Fallback
                
                if match_key not in merged_stats:
                    merged_stats[match_key] = {"wins": 0, "count": 0}
                
                count = data.get('count', 0)
                win_rate = data.get('win_rate', 0.0)
                # Reconstruct wins from rate * count
                wins = win_rate * count
                
                merged_stats[match_key]["count"] += count
                merged_stats[match_key]["wins"] += wins

        # 3. Generate Evolution Report
        # Ensure Engineer sees the full, merged stats
        hr_context = {
            "cio_report": "HR_PROTOCOL_INITIATED",
            "performance_stats": merged_stats,
            "task": "Generate Monthly System Evolution Report"
        }
        
        optimizations = engineer.run(hr_context)
        
        # Format stats into Markdown table
        stats_md = "\n| Agent (分析師) | Win Rate (勝率) | Count (次數) | Status (狀態) |\n|---|---|---|---|\n"

        # Generate Table Rows (Sort by predefined order for consistency)
        display_order = [a for a in target_agents if a in merged_stats] + [a for a in merged_stats if a not in target_agents]
        
        for agent in display_order:
             data = merged_stats[agent]
             count = data["count"]
             raw_wins = data["wins"]
             win_rate = raw_wins / count if count > 0 else 0.0
             
             # Determine status icon
             if count < 5:
                 status = "⚪️ 數據不足 (Insufficient Data)"
             elif win_rate >= 0.6:
                 status = "🟢 優異 (Excellent)"
             elif win_rate <= 0.4:
                 status = "🔴 待優化 (Needs Imp.)"
             else:
                 status = "🟡 正常 (Normal)"
             
             stats_md += f"| {agent} | {win_rate:.1%} | {count} | {status} |\n"

        report_content = f"""# 月度系統進化報告 (System Evolution Report)
日期: {datetime.now().strftime('%Y-%m-%d')}

## 1. 效能概覽 (Performance Overview)
{stats_md}

## 2. 優化行動 (APO Cycle)
"""
        if optimizations:
            for opt in optimizations:
                if "error" in opt:
                    report_content += f"- [錯誤] {opt['error']}\n"
                else:
                    report_content += f"- [已優化] {opt.get('target_agent', 'Unknown')}: {opt.get('reason', 'N/A')}\n"
                    if opt.get('diff'):
                        report_content += f"  - 變更 (Diff):\n```diff\n{opt.get('diff')}\n```\n"
        else:
            report_content += "-系統運作正常，未觸發關鍵優化 (System functioning within parameters)。\n"
            
        report_content += "\n## 3. 未來規劃 (Future Roadmap)\n- 持續監控「風險控管明確度 (Risk Control Specificity)」。\n"
        
        # 4. Send Email
        notifier = EmailNotifier()
        notifier.send_report("月度系統進化報告 (System Evolution Report)", report_content)
        logger.info("Monthly Refinement Report sen successfully.")
        
    except Exception as e:
        logger.error(f"Monthly Refinement Failed: {e}")
        raise e

if __name__ == "__main__":
    main()
