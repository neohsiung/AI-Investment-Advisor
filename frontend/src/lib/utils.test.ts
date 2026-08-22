import { describe, expect, it } from "vitest";

import { cn, formatCurrency, formatPercentage } from "./utils";

describe("cn", () => {
  it("merges conflicting tailwind classes, last one winning", () => {
    expect(cn("p-2", "p-4")).toBe("p-4");
  });

  it("drops falsy branches", () => {
    expect(cn("base", false && "hidden", undefined, "active")).toBe("base active");
  });
});

describe("formatCurrency", () => {
  it("formats as USD", () => {
    expect(formatCurrency(1234.5)).toBe("$1,234.50");
  });

  it("keeps the sign on negatives — a loss must never read as a gain", () => {
    expect(formatCurrency(-42)).toBe("-$42.00");
  });

  it("renders zero rather than an empty string", () => {
    expect(formatCurrency(0)).toBe("$0.00");
  });
});

describe("formatPercentage", () => {
  // The argument is already in percent units and the formatter divides by 100.
  // Getting this backwards renders 12.4% as 1240% on the portfolio surface, so
  // the unit contract is pinned here rather than left to the call sites.
  // 參數本身即為百分比數值，函式內部再除以 100；搞反會把 12.4% 顯示成 1240%。
  it("treats the input as percent units, not a ratio", () => {
    expect(formatPercentage(12.4)).toBe("+12.40%");
  });

  it("shows an explicit plus for gains and a minus for losses", () => {
    expect(formatPercentage(3)).toBe("+3.00%");
    expect(formatPercentage(-3)).toBe("-3.00%");
  });

  it("shows no sign at zero", () => {
    expect(formatPercentage(0)).toBe("0.00%");
  });
});
