import { Loader2 } from "lucide-react";

const ORDINARY_LINE = "資產中心初始化中...";
const CLOSED_LINE = "紐約今天休市，美股不開盤";

export type MarketState = "closed" | "trading_day" | "unknown";

/** Only a confirmed closed day changes the line; anything else keeps the ordinary text. */
export function loadingLine(state?: MarketState): string {
  return state === "closed" ? CLOSED_LINE : ORDINARY_LINE;
}

export function DashboardLoading({ marketState }: { marketState?: MarketState }) {
  return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <div className="flex flex-col items-center gap-4">
        <Loader2 className="h-10 w-10 text-primary animate-spin" />
        <p className="text-xs font-label uppercase tracking-widest text-on-surface-variant opacity-60">
          {loadingLine(marketState)}
        </p>
      </div>
    </div>
  );
}
