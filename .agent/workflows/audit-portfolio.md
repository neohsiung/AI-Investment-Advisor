---
description: Workflow for auditing and aligning portfolio metrics (NLV, Profit, Cash) to ensure data integrity and stability.
---

# /audit-portfolio Workflow

Use this workflow when the user reports discrepancies between the Dashboard and Broker or when setting up a new user/environment.

## 1. Preflight Check

1. Read the `portfolio-data-verification` skill to understand the methodology:
   `view_file path="/Users/neohsiung/Work/go/investment-advisor/.agent/skills/portfolio-data-verification/SKILL.md"`

## 2. Quantitative Verification

1. Run the verification script to get the current state:

   ```bash
   docker exec -i investment_advisor_dashboard /usr/local/bin/python -c "from src.services.dashboard_service import DashboardService; data = DashboardService().prepare_dashboard_data('USER_ID'); print(data['metrics'])"
   ```

2. Identify the target values (NLV, Profit, Cash).
3. Check the `transactions` table for any internal drift or incorrect historical entries.

## 3. Data Alignment

1. **Cash Balance**: If off, add a `CASH` action transaction with ticker `USD` or `ETORO_SYNC`.
2. **NLV/Profit**: If the ROI doesn't reflect actual user transfers, use `calculate_net_invested_capital` to calibrate and add `NLV_ADJUST` or `STABILIZE_CAP` transactions if necessary.
3. **Static Anchors**: Ensure tickers starting with `__ANCHOR_` or `STABILIZE_` are present if a fixed baseline is required.

## 4. UI/UX Verification

1. Verify that tooltips are functional by checking `.saas-tooltip` in `src/styles/design_system.css`.
2. Ensure `Standardize Profit` logic is applied in `DashboardService`.

## 5. Final Confirmation

1. Present a clear table comparing `Current` vs `Target` values to the user.
