"""
Weekly cost reporting and optimization recommendations service.
Generates markdown reports for weekly analysis and decision-making.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List
from src.infrastructure.llm.cost_attribution import CostAttributionService

logger = logging.getLogger("WeeklyCostReportService")


class WeeklyCostReportService:
    """
    Service for generating comprehensive weekly LLM cost reports.
    Includes breakdowns by cognitive layer, optimization recommendations, and trends.
    """
    
    BUDGET_WEEKLY = 20.0
    BUDGET_SOFT_LIMIT = 16.0  # 80%
    BUDGET_HARD_LIMIT = 20.0  # 100%
    
    def __init__(self):
        """Initialize report service."""
        self.attribution = CostAttributionService()
    
    def generate_report(self, user_id: str) -> Dict:
        """
        Generate comprehensive weekly cost report.
        
        Returns:
            Dictionary with summary, breakdown, and recommendations
        """
        breakdown = self.attribution.get_weekly_breakdown(user_id, days=7)
        recommendations = self.attribution.get_optimization_recommendations(user_id)
        
        total_cost = breakdown.get("total_cost_usd", 0.0)
        
        report = {
            "generated_at": datetime.utcnow().isoformat(),
            "user_id": user_id,
            "period": "7 days",
            "summary": {
                "total_cost_usd": total_cost,
                "budget_weekly": self.BUDGET_WEEKLY,
                "budget_remaining": self.BUDGET_WEEKLY - total_cost,
                "budget_utilization_pct": (total_cost / self.BUDGET_WEEKLY * 100),
                "budget_status": self._get_budget_status(total_cost)
            },
            "by_cognitive_layer": breakdown.get("by_layer", {}),
            "recommendations": recommendations,
            "error": breakdown.get("error")
        }
        
        return report
    
    def _get_budget_status(self, current_cost: float) -> str:
        """Determine budget status based on spending."""
        if current_cost >= self.BUDGET_HARD_LIMIT:
            return "CRITICAL"
        elif current_cost >= self.BUDGET_SOFT_LIMIT:
            return "WARNING"
        elif current_cost >= self.BUDGET_WEEKLY * 0.5:
            return "HEALTHY"
        else:
            return "EXCELLENT"
    
    def format_markdown_report(self, report: Dict) -> str:
        """
        Format report as markdown for display or sharing.
        
        Args:
            report: Report dictionary from generate_report()
        
        Returns:
            Formatted markdown string
        """
        lines = [
            "# 📊 Weekly LLM Cost Report",
            f"**Generated**: {report['generated_at']}",
            f"**User**: {report['user_id']}",
            f"**Period**: {report['period']}",
            ""
        ]
        
        summary = report["summary"]
        status_emoji = self._get_status_emoji(summary["budget_status"])
        
        lines.extend([
            "## Summary",
            f"{status_emoji} **Budget Status**: {summary['budget_status']}",
            f"- **Total Cost**: ${summary['total_cost_usd']:.2f} / ${summary['budget_weekly']:.2f}",
            f"- **Budget Remaining**: ${summary['budget_remaining']:.2f}",
            f"- **Budget Utilization**: {summary['budget_utilization_pct']:.1f}%",
            ""
        ])
        
        # Cognitive layer breakdown table
        by_layer = report["by_cognitive_layer"]
        if by_layer:
            lines.extend([
                "## Cost Breakdown by Cognitive Layer",
                "| Layer | Requests | Tokens | Input | Output | Cost | % |",
                "|-------|----------|--------|-------|--------|------|---|"
            ])
            
            for layer_name in ["nano", "fast", "smart", "advanced"]:
                if layer_name in by_layer:
                    data = by_layer[layer_name]
                    lines.append(
                        f"| {layer_name} | {data['request_count']} | "
                        f"{data['total_tokens']:,} | {data['input_tokens']:,} | "
                        f"{data['output_tokens']:,} | "
                        f"${data['total_cost_usd']:.4f} | {data['pct_of_total']:.1f}% |"
                    )
            
            lines.append("")
        
        # Recommendations
        recommendations = report.get("recommendations", [])
        if recommendations:
            lines.extend([
                "## 🎯 Optimization Recommendations",
                f"*{len(recommendations)} opportunity(ies) identified*",
                ""
            ])
            
            for i, rec in enumerate(recommendations, 1):
                severity_emoji = {
                    "HIGH": "🔴",
                    "MEDIUM": "🟡",
                    "LOW": "🟢"
                }.get(rec["severity"], "⚪")
                
                lines.extend([
                    f"### {severity_emoji} {i}. {rec['type']}",
                    rec["message"],
                    f"*Potential savings: **${rec['potential_savings']:.2f}** / week*",
                    ""
                ])
        else:
            lines.extend([
                "## 🎯 Optimization Recommendations",
                "*No optimization opportunities detected. Current usage is optimal.*",
                ""
            ])
        
        # Footer with trend indicators
        lines.extend([
            "---",
            "📈 **Trend Indicators**:",
            f"- Previous week comparison: Not yet available (first report)",
            f"- Forecast: If current trend continues, weekly spend: ${summary['total_cost_usd']:.2f}",
            ""
        ])
        
        return "\n".join(lines)
    
    def _get_status_emoji(self, status: str) -> str:
        """Get emoji for budget status."""
        return {
            "CRITICAL": "🚨",
            "WARNING": "⚠️",
            "HEALTHY": "✅",
            "EXCELLENT": "🌟"
        }.get(status, "❓")
    
    def format_html_report(self, report: Dict) -> str:
        """
        Format report as HTML for web display.
        
        Args:
            report: Report dictionary from generate_report()
        
        Returns:
            HTML string
        """
        summary = report["summary"]
        by_layer = report["by_cognitive_layer"]
        
        html_parts = [
            "<!DOCTYPE html>",
            "<html>",
            "<head>",
            '<meta charset="UTF-8">',
            "<title>Weekly LLM Cost Report</title>",
            "<style>",
            "body { font-family: Arial, sans-serif; margin: 20px; }",
            ".summary { background: #f0f0f0; padding: 15px; border-radius: 5px; }",
            ".layer-row { padding: 10px; border-bottom: 1px solid #ddd; }",
            ".critical { color: #d32f2f; }",
            ".warning { color: #f57c00; }",
            ".healthy { color: #388e3c; }",
            ".table { width: 100%; border-collapse: collapse; }",
            ".table th { background: #1976d2; color: white; padding: 10px; }",
            ".table td { padding: 10px; }",
            "</style>",
            "</head>",
            "<body>"
        ]
        
        # Title and summary
        html_parts.extend([
            "<h1>📊 Weekly LLM Cost Report</h1>",
            f"<p><strong>Generated:</strong> {report['generated_at']}</p>",
            f"<p><strong>User:</strong> {report['user_id']}</p>",
            "<div class='summary'>",
            f"<h2>Summary</h2>",
            f"<p><strong>Total Cost:</strong> ${summary['total_cost_usd']:.2f} / ${summary['budget_weekly']:.2f}</p>",
            f"<p><strong>Budget Remaining:</strong> ${summary['budget_remaining']:.2f}</p>",
            f"<p><strong>Budget Utilization:</strong> {summary['budget_utilization_pct']:.1f}%</p>",
            f"<p class='{summary['budget_status'].lower()}'><strong>Status:</strong> {summary['budget_status']}</p>",
            "</div>"
        ])
        
        # Layer breakdown table
        if by_layer:
            html_parts.extend([
                "<h2>Cost Breakdown by Cognitive Layer</h2>",
                "<table class='table'>",
                "<tr><th>Layer</th><th>Requests</th><th>Tokens</th><th>Cost</th><th>% of Total</th></tr>"
            ])
            
            for layer_name in ["nano", "fast", "smart", "advanced"]:
                if layer_name in by_layer:
                    data = by_layer[layer_name]
                    html_parts.append(
                        f"<tr><td>{layer_name}</td><td>{data['request_count']}</td>"
                        f"<td>{data['total_tokens']:,}</td>"
                        f"<td>${data['total_cost_usd']:.4f}</td>"
                        f"<td>{data['pct_of_total']:.1f}%</td></tr>"
                    )
            
            html_parts.append("</table>")
        
        # Close
        html_parts.extend([
            "</body>",
            "</html>"
        ])
        
        return "\n".join(html_parts)
    
    def save_report_to_file(self, report: Dict, filename: str, format: str = "markdown") -> bool:
        """
        Save report to file.
        
        Args:
            report: Report dictionary
            filename: Output filename
            format: "markdown" or "html"
        
        Returns:
            True if successful
        """
        try:
            if format.lower() == "markdown":
                content = self.format_markdown_report(report)
            elif format.lower() == "html":
                content = self.format_html_report(report)
            else:
                raise ValueError(f"Unknown format: {format}")
            
            with open(filename, "w") as f:
                f.write(content)
            
            logger.info(f"Report saved to {filename}")
            return True
        
        except Exception as e:
            logger.error(f"Failed to save report: {e}")
            return False
