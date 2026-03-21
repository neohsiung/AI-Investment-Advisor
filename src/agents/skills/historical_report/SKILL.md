---
name: get_historical_report
description: Fetch a historical investment report (e.g., last week's WeeklyWorkflow) to compare current signals and justify strategy adjustments.
metadata:
  openclaw:
    author: System
    os: ["linux", "darwin"]
---

# get_historical_report

Use this skill when you need to understand the strategic narrative or the reasoning behind the portfolio adjustments from a previous period, particularly the previous week.
You should call this tool when performing the `Report Synthesis` or `Market Cycle Analysis` tasks to compare current market conditions with last week's conditions and to explicitly document why any new changes are being made.

Pass the `report_type` (default "WeeklyWorkflow") and `weeks_ago` (default 1) to fetch the desired report.
