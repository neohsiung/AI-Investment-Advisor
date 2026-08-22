import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import HealthPage from "./page";

// The loop-health page is where a human checks whether the system is actually
// working. Its three failure modes all matter: showing stale numbers as live,
// showing "healthy" when the fetch failed, and rendering a blank where a metric
// should be. The 2026-08-10 outage ran for three days with every monitor green,
// so a monitoring surface that cannot distinguish "no data" from "zero" is not
// a monitoring surface.
// 這頁是人類判斷系統是否真的在運作的地方；抓取失敗卻顯示正常、或把「沒有資料」
// 畫成 0，正是 8/10 停擺三天而所有監控全綠的形狀。
const useSWRMock = vi.fn();
vi.mock("swr", () => ({
  default: (key: string | null, ...rest: unknown[]) => useSWRMock(key, ...rest),
}));

const DATA = {
  status: "ok",
  learning: {
    decisions_total: 42,
    decisions_resolved: 12,
    resolution_rate: 0.2857,
    rules_by_status: { active: 7, candidate: 3, superseded: 2 },
    avg_active_rule_score: 0.1234,
  },
  self_ops: {
    breaches_this_week: 1,
    remediation_by_tier: { T1: 2, T2: 1, T3: 0 },
    weekly_cost_usd: 4.21,
    weekly_budget_usd: 20,
  },
  feedback: {
    approval_rate: 0.75,
    by_decision: { approved: 6, rejected: 2 },
    rejection_reason_capture_rate: 0.5,
    preference_sample_size: 8,
    risk_appetite_score: 0.42,
  },
  caching: {
    total_workflow_runs: 30,
    cache_hits: 18,
    cache_misses: 12,
    saved_cost_usd: 1.5,
  },
};

beforeEach(() => {
  useSWRMock.mockReset();
});

function mock(state: Record<string, unknown>) {
  useSWRMock.mockReturnValue({ data: undefined, error: undefined, isLoading: false, ...state });
}

describe("HealthPage", () => {
  it("polls, rather than showing a snapshot that silently goes stale", () => {
    mock({ data: DATA });
    render(<HealthPage />);

    const [key, , options] = useSWRMock.mock.calls[0];
    expect(key).toBe("/api/v1/loop-health");
    expect((options as { refreshInterval?: number })?.refreshInterval).toBeGreaterThan(0);
  });

  it("shows a loading state instead of an empty dashboard", () => {
    mock({ isLoading: true });
    render(<HealthPage />);

    expect(screen.getByText(/載入系統健康數據中/)).toBeInTheDocument();
  });

  it("reports a fetch failure as a failure — never as healthy zeros", () => {
    mock({ error: { message: "Network Error" } });
    render(<HealthPage />);

    expect(screen.getByText("無法載入監控數據")).toBeInTheDocument();
    expect(screen.getByText(/Network Error/)).toBeInTheDocument();
    expect(screen.queryByText("總決策數")).not.toBeInTheDocument();
  });

  it("treats a 200 with no body as an error, not as an empty system", () => {
    // `data` undefined with no error would otherwise destructure to a crash or
    // a page of blanks that reads like "nothing has happened yet".
    mock({ data: undefined });
    render(<HealthPage />);

    expect(screen.getByText("無法載入監控數據")).toBeInTheDocument();
  });

  it("surfaces the backend detail message when there is one", () => {
    mock({ error: { response: { data: { detail: "loop-health query timed out" } } } });
    render(<HealthPage />);

    expect(screen.getByText("loop-health query timed out")).toBeInTheDocument();
  });

  it("renders the learning-loop metrics from the payload", () => {
    mock({ data: DATA });
    render(<HealthPage />);

    expect(screen.getByText("42")).toBeInTheDocument();
    expect(screen.getByText("已結算決策: 12 筆")).toBeInTheDocument();
    expect(screen.getByText("28.6%")).toBeInTheDocument();
  });

  it("renders a null metric as an em dash, not as zero", () => {
    // A missing rate and a genuine 0% mean opposite things: one is "no data
    // yet", the other is "nothing was ever approved".
    // 缺值與真正的 0% 意義相反：前者是還沒有資料，後者是從來沒有通過。
    mock({
      data: {
        ...DATA,
        learning: { ...DATA.learning, resolution_rate: null, avg_active_rule_score: null },
      },
    });
    render(<HealthPage />);

    expect(screen.getByText("N/A")).toBeInTheDocument();
    expect(screen.queryByText("0.0%")).not.toBeInTheDocument();
  });

  it("tolerates a payload with no caching block", () => {
    // `caching` is optional in the response type; an older backend omits it.
    const { caching, ...withoutCaching } = DATA;
    mock({ data: withoutCaching });

    expect(() => render(<HealthPage />)).not.toThrow();
    expect(screen.getByText("42")).toBeInTheDocument();
  });

  it("renders missing rule-status counts as 0 rather than undefined", () => {
    mock({ data: { ...DATA, learning: { ...DATA.learning, rules_by_status: {} } } });
    render(<HealthPage />);

    expect(screen.getByText(/候選 \(Candidate\): 0/)).toBeInTheDocument();
    expect(screen.queryByText(/undefined/)).not.toBeInTheDocument();
  });
});
