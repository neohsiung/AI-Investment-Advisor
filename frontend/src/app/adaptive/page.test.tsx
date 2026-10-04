import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AdaptiveWarRoomPage from "./page";

const swrMock = vi.fn();
vi.mock("swr", () => ({
  default: (key: string | null, ...rest: unknown[]) => swrMock(key, ...rest),
}));

const MOCK_DIAGNOSE_DATA = {
  status: "success",
  data: {
    health_score: 86.4,
    health_rating: "OPTIMAL",
    radar_dimensions: {
      regime_alignment: 85.0,
      diversification_efficiency: 90.0,
      factor_balance: 82.0,
      tail_risk_resilience: 88.0,
      capital_safety: 95.0,
    },
    regime_analysis: {
      current_regime: "BULL_LOW_VOL",
      regime_confidence: 0.88,
      target_cash_buffer: 0.10,
      target_beta: 1.05,
      description: "低波動牛市體制",
    },
    tail_risk_analysis: {
      alert_level: "NORMAL",
      var_999: 0.042,
      cvar_999: 0.058,
      fat_tail_ratio: 1.25,
      kurtosis: 2.8,
    },
    diversification_metrics: {
      effective_n: 3.8,
      max_weight: 0.35,
      gini_coefficient: 0.25,
    },
    capital_safety_metrics: {
      leverage_ratio: 1.0,
      margin_cushion: 0.35,
      max_drawdown: 0.05,
    },
    rebalance_recommendation: {
      needs_rebalance: false,
      rebalance_reason: "投組結構吻合低波動牛市體制，維持現有配置",
      target_weights: {
        SPY: 0.35,
        QQQ: 0.25,
        TLT: 0.15,
        GLD: 0.05,
        CASH: 0.20,
      },
      trades: [],
    },
    summary_insights: [
      "五維健康總評分為 86.4/100，整體配置處於 OPTIMAL 狀態。",
      "當前宏觀體制判定為 BULL_LOW_VOL (信心度 88%)。",
      "極值理論 (EVT) 尾部風險處於 NORMAL 常態水準。",
    ],
    provenance: {
      holdings: "live",
      market_observation: "live",
      tail_risk: "weighted_assets",
    },
  },
};

beforeEach(() => {
  swrMock.mockReset();
});

function mock(state: Record<string, unknown>) {
  swrMock.mockReturnValue({
    data: undefined,
    error: undefined,
    isLoading: false,
    isValidating: false,
    mutate: vi.fn(),
    ...state,
  });
}

describe("AdaptiveWarRoomPage", () => {
  it("polls SWR with refreshInterval rather than stale snapshot", () => {
    mock({ data: MOCK_DIAGNOSE_DATA });
    render(<AdaptiveWarRoomPage />);

    const [key, , options] = swrMock.mock.calls[0];
    expect(key).toBe("/api/v1/adaptive-intelligence/diagnose");
    expect((options as { refreshInterval?: number })?.refreshInterval).toBeGreaterThan(0);
  });

  it("shows an explicit loading state instead of blank components", () => {
    mock({ isLoading: true });
    render(<AdaptiveWarRoomPage />);

    expect(screen.getByText(/正在運算自適應風控協同診斷數據/)).toBeInTheDocument();
  });

  it("reports fetch failure with detail message and retry action", () => {
    mock({
      error: {
        response: {
          data: { detail: "Postgres connection error in adaptive service" },
        },
      },
    });
    render(<AdaptiveWarRoomPage />);

    expect(screen.getByText("自適應戰情室診斷載入失敗")).toBeInTheDocument();
    expect(screen.getByText(/Postgres connection error in adaptive service/)).toBeInTheDocument();
    expect(screen.getByText("重試連線")).toBeInTheDocument();
    expect(screen.queryByText("綜合健康分數")).not.toBeInTheDocument();
  });

  it("renders health score, rating capsule and core cards correctly", () => {
    mock({ data: MOCK_DIAGNOSE_DATA });
    render(<AdaptiveWarRoomPage />);

    expect(screen.getByText("86.4")).toBeInTheDocument();
    expect(screen.getByText("OPTIMAL (極佳)")).toBeInTheDocument();
    expect(screen.getByText("BULL_LOW_VOL")).toBeInTheDocument();
    expect(screen.getByText("88%")).toBeInTheDocument();
    expect(screen.getByText("1.25x")).toBeInTheDocument();
    expect(screen.getByText("3.8")).toBeInTheDocument();
  });

  it("displays provenance badges reflecting live data vs fallbacks", () => {
    mock({ data: MOCK_DIAGNOSE_DATA });
    render(<AdaptiveWarRoomPage />);

    expect(screen.getByText("持倉: 實測持倉 (Live)")).toBeInTheDocument();
    expect(screen.getByText("宏觀: 即時行情 (Live SPY/VIX)")).toBeInTheDocument();
    expect(screen.getByText("尾部來源: 加權行情 (Asset-Weighted)")).toBeInTheDocument();
  });

  it("displays template and synthetic provenance badges when fallback is used", () => {
    const fallbackData = {
      ...MOCK_DIAGNOSE_DATA,
      data: {
        ...MOCK_DIAGNOSE_DATA.data,
        provenance: {
          holdings: "template",
          market_observation: "default",
          tail_risk: "synthetic",
        },
      },
    };
    mock({ data: fallbackData });
    render(<AdaptiveWarRoomPage />);

    expect(screen.getByText("持倉: 範本基準 (Template)")).toBeInTheDocument();
    expect(screen.getByText("宏觀: 預設常數 (Default)")).toBeInTheDocument();
    expect(screen.getByText("尾部來源: 合成模擬 (Synthetic)")).toBeInTheDocument();
  });

  it("renders accessible table representation for radar dimensions", () => {
    mock({ data: MOCK_DIAGNOSE_DATA });
    render(<AdaptiveWarRoomPage />);

    const table = screen.getByRole("table", { name: "五維健康雷達數據表" });
    expect(table).toBeInTheDocument();

    expect(screen.getByRole("cell", { name: "體制適應度" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "分散化效率" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "因子風格平衡" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "尾部風險抗跌" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "資本安全度" })).toBeInTheDocument();
  });

  it("renders rebalance suggestions and summary insights", () => {
    mock({ data: MOCK_DIAGNOSE_DATA });
    render(<AdaptiveWarRoomPage />);

    expect(screen.getByText("配置穩健")).toBeInTheDocument();
    expect(screen.getByText(/投組結構吻合低波動牛市體制/)).toBeInTheDocument();
    expect(
      screen.getByText("五維健康總評分為 86.4/100，整體配置處於 OPTIMAL 狀態。")
    ).toBeInTheDocument();
  });

  it("supports flat summary payload from health endpoint seamlessly", () => {
    const flatHealthPayload = {
      status: "success",
      health_score: 74.2,
      health_rating: "BALANCED",
      radar: {
        regime_alignment: 70.0,
        diversification_efficiency: 80.0,
        factor_balance: 75.0,
        tail_risk_resilience: 72.0,
        capital_safety: 85.0,
      },
      current_regime: "SIDEWAYS_HIGH_VOL",
      regime_confidence: 0.65,
      needs_rebalance: true,
      summary_insights: ["體制轉移至高波動震盪，建議提高現金儲備。"],
      provenance: {
        holdings: "live",
        market_observation: "live",
        tail_risk: "live_portfolio",
      },
    };

    mock({ data: flatHealthPayload });
    render(<AdaptiveWarRoomPage />);

    expect(screen.getByText("74.2")).toBeInTheDocument();
    expect(screen.getByText("BALANCED (穩健)")).toBeInTheDocument();
    expect(screen.getByText("SIDEWAYS_HIGH_VOL")).toBeInTheDocument();
    expect(screen.getByText("65%")).toBeInTheDocument();
    expect(screen.getByText("尾部來源: 實測淨值 (Live Portfolio)")).toBeInTheDocument();
    expect(screen.getByText("建議調倉")).toBeInTheDocument();
  });
});
