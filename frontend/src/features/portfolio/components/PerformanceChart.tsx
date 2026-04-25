"use client";

import React from "react";
import useSWR from "swr";
import { 
  AreaChart, 
  Area, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  ResponsiveContainer
} from "recharts";
import { PortfolioRepository } from "../infra/PortfolioRepository";
import { formatCurrency } from "@/lib/utils";
import { Loader2 } from "lucide-react";

export function PerformanceChart() {
  const { data: history, isLoading } = useSWR(
    "/api/v1/dashboard/performance/history",
    () => PortfolioRepository.getPerformanceHistory(),
    { refreshInterval: 600000 } // 10 mins
  );

  if (isLoading) {
    return (
      <div className="h-64 w-full flex items-center justify-center bg-surface-container/5 rounded-lg border border-dashed border-outline-variant/20">
        <Loader2 className="h-6 w-6 text-primary animate-spin" />
      </div>
    );
  }

  if (!history || history.length === 0) {
    return (
      <div className="h-64 w-full flex items-center justify-center bg-surface-container/5 rounded-lg border border-dashed border-outline-variant/20">
        <p className="font-label text-[10px] uppercase tracking-widest text-on-surface-variant opacity-50 italic">尚未有足夠的歷史數據進行繪製</p>
      </div>
    );
  }

  // Format data for Recharts (assuming data has 'date', 'total_nlv', 'pnl')
  const chartData = history.map(d => ({
    ...d,
    dateValue: new Date(d.date).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }),
    nlv: parseFloat(d.total_nlv || 0),
    pnl: parseFloat(d.pnl || 0),
  }));

  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="colorNlv" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="var(--primary)" stopOpacity={0.3}/>
              <stop offset="95%" stopColor="var(--primary)" stopOpacity={0}/>
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="rgba(var(--outline-variant-rgb), 0.1)" />
          <XAxis 
            dataKey="dateValue" 
            axisLine={false} 
            tickLine={false} 
            tick={{ fontSize: 9, fill: "var(--on-surface-variant)" }} 
            dy={10}
          />
          <YAxis 
            axisLine={false} 
            tickLine={false} 
            tick={{ fontSize: 9, fill: "var(--on-surface-variant)" }} 
            tickFormatter={(val) => `$${(val / 1000).toFixed(0)}k`}
            dx={-10}
          />
          <Tooltip 
            contentStyle={{ 
              backgroundColor: "var(--surface-container-highest)", 
              borderColor: "var(--outline-variant)",
              borderRadius: "8px",
              fontSize: "12px",
              boxShadow: "0 10px 15px -3px rgba(0, 0, 0, 0.1)"
            }}
            formatter={(value: any) => [formatCurrency(value), "資產淨值 (NLV)"]}
          />
          <Area 
            type="monotone" 
            dataKey="nlv" 
            stroke="var(--primary)" 
            strokeWidth={3}
            fillOpacity={1} 
            fill="url(#colorNlv)" 
            animationDuration={1500}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
