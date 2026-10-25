import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PortfolioStats } from "./PortfolioStats";

const noop = vi.fn();

function renderStats(summary: Record<string, unknown> | undefined) {
  return render(
    <PortfolioStats
      summary={summary}
      isReporting={false}
      isRebalancing={false}
      onGenerateReport={noop}
      onRebalance={noop}
    />
  );
}

describe("PortfolioStats", () => {
  it("shows no change percentage when net liquidation value is zero", () => {
    renderStats({ total_valuation: 0, uninvested_cash: 0, roi_percentage: 0 });

    expect(screen.getByText("核心投資組合")).toBeInTheDocument();
    expect(screen.queryByText(/[+-]\d+(\.\d+)?%/)).not.toBeInTheDocument();
  });

  it("shows no change percentage when there is no summary at all", () => {
    renderStats(undefined);

    expect(screen.queryByText(/[+-]\d+(\.\d+)?%/)).not.toBeInTheDocument();
  });

  it("does not invent a risk exposure label when the backend gives none", () => {
    renderStats({ total_valuation: 0 });

    expect(screen.queryByText(/MODERATE/i)).not.toBeInTheDocument();
  });

  it("shows the real ROI next to the title once there is a portfolio", () => {
    renderStats({ total_valuation: 12000, uninvested_cash: 500, roi_percentage: 3.5 });

    expect(screen.getByLabelText("投組報酬率")).toHaveTextContent("+3.50%");
  });

  it("never shows a negative sign on a ROI that rounds to zero", () => {
    renderStats({ total_valuation: 9000, roi_percentage: -0.004 });

    expect(screen.getByLabelText("投組報酬率")).toHaveTextContent(/^0\.00%$/);
    expect(screen.queryByText("-0.00%")).not.toBeInTheDocument();
  });

  it("shows a negative ROI with its sign", () => {
    renderStats({ total_valuation: 9000, roi_percentage: -1.25 });

    expect(screen.getByLabelText("投組報酬率")).toHaveTextContent("-1.25%");
  });
});
