import React from "react";
import TacticalCard from "@/components/ui/TacticalCard";
import { formatCurrency, cn } from "@/lib/utils";

interface PositionsTableProps {
  positions: any[];
  isLoading: boolean;
}

export function PositionsTable({ positions, isLoading }: PositionsTableProps) {
  if (isLoading) {
    return (
      <TacticalCard title="目前持倉與行動指引 (Positions & Action Guidelines)">
        <div className="py-12 flex justify-center">
          <div className="animate-pulse flex space-x-4 w-full px-4">
            <div className="rounded-full bg-surface-container-highest h-10 w-10"></div>
            <div className="flex-1 space-y-6 py-1">
              <div className="h-2 bg-surface-container-highest rounded"></div>
              <div className="grid grid-cols-3 gap-4">
                <div className="h-2 bg-surface-container-highest rounded col-span-2"></div>
                <div className="h-2 bg-surface-container-highest rounded col-span-1"></div>
              </div>
            </div>
          </div>
        </div>
      </TacticalCard>
    );
  }

  return (
    <TacticalCard title="目前持倉與行動指引 (Positions & Action Guidelines)">
      {/* 1. Desktop View (Table) - Visible on md and up */}
      <div className="hidden md:block overflow-x-auto">
        <table className="w-full text-left font-body">
          <thead>
            <tr className="bg-surface-container-highest/30">
              <th className="py-3 px-4 font-label text-[10px] uppercase tracking-widest text-on-surface-variant font-bold">資產 (Ticker)</th>
              <th className="py-3 px-4 font-label text-[10px] uppercase tracking-widest text-on-surface-variant font-bold">數量 (Qty)</th>
              <th className="py-3 px-4 font-label text-[10px] uppercase tracking-widest text-on-surface-variant font-bold">市價 (Price)</th>
              <th className="py-3 px-4 font-label text-[10px] uppercase tracking-widest text-on-surface-variant font-bold text-center">損益 (P/L)</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-outline-variant/10 text-sm">
            {positions.length > 0 ? (
              positions.map((pos: any) => (
                <tr key={pos.ticker} className="hover:bg-surface-bright/50 transition-colors">
                  <td className="py-4 px-4 font-bold font-mono tracking-tight">{pos.ticker}</td>
                  <td className="py-4 px-4 font-mono">{pos.quantity?.toFixed(4)}</td>
                  <td className="py-4 px-4 font-mono">{formatCurrency(pos.current_price)}</td>
                  <td className="py-4 px-4 text-center">
                    <span className={cn(
                        "px-3 py-1 rounded-full text-[10px] font-bold font-label uppercase tracking-wider shadow-sm border",
                        (pos.unrealized_pnl || 0) >= 0 ? "bg-secondary/10 text-secondary border-secondary/20" : "bg-error/10 text-error border-error/20"
                    )}>
                      {formatCurrency(pos.unrealized_pnl || 0)}
                    </span>
                  </td>
                </tr>
              ))
            ) : (
              <tr><td colSpan={4} className="py-12 text-center opacity-50 italic uppercase text-[10px]">No active positions</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {/* 2. Mobile View (Card List) - Visible on screens below md */}
      <div className="md:hidden space-y-3">
        {positions.length > 0 ? (
          positions.map((pos: any) => (
            <div key={pos.ticker} className="p-4 rounded-xl bg-surface-container-low border border-outline-variant/10 shadow-sm">
              <div className="flex justify-between items-start mb-3">
                <div className="font-bold font-mono text-lg tracking-tight text-primary">{pos.ticker}</div>
                <span className={cn(
                    "px-2 py-0.5 rounded text-[9px] font-bold font-label uppercase tracking-wider border",
                    (pos.unrealized_pnl || 0) >= 0 ? "bg-secondary/10 text-secondary border-secondary/20" : "bg-error/10 text-error border-error/20"
                )}>
                  {formatCurrency(pos.unrealized_pnl || 0)}
                </span>
              </div>
              <div className="grid grid-cols-2 gap-4 text-[10px] font-label text-on-surface-variant uppercase tracking-widest">
                <div>
                  <div className="opacity-60 mb-1">數量 (Qty)</div>
                  <div className="text-on-surface font-mono text-xs">{pos.quantity?.toFixed(4)}</div>
                </div>
                <div className="text-right">
                  <div className="opacity-60 mb-1">市價 (Price)</div>
                  <div className="text-on-surface font-mono text-xs">{formatCurrency(pos.current_price)}</div>
                </div>
              </div>
            </div>
          ))
        ) : (
          <div className="py-12 text-center opacity-50 italic uppercase text-[10px]">No active positions</div>
        )}
      </div>
    </TacticalCard>
  );
}
