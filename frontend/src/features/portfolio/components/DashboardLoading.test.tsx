import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DashboardLoading, loadingLine, type MarketState } from "./DashboardLoading";

// The loading line may only state a fact the server confirmed. "unknown" and a missing answer must show the
// ordinary line: guessing "open" or "closed" about a system that moves real money is worse than saying nothing.
// 載入那行只能說伺服器確認過的事實；unknown 與沒有答案都顯示一般文字，不猜開市或休市。
describe("DashboardLoading", () => {
  it("says the US market is closed when the server says closed", () => {
    render(<DashboardLoading marketState="closed" />);
    expect(screen.getByText("紐約今天休市，美股不開盤")).toBeInTheDocument();
  });

  it.each<MarketState | undefined>(["trading_day", "unknown", undefined])("keeps the ordinary line for %s", (state) => {
    expect(loadingLine(state)).toBe("資產中心初始化中...");
  });

  it("renders the ordinary line while the answer has not arrived", () => {
    render(<DashboardLoading />);
    expect(screen.getByText("資產中心初始化中...")).toBeInTheDocument();
  });
});
