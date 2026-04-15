/**
 * API v1 Unified TypeScript Interfaces
 * Generated to match backend Pydantic DTOs in src/api/v1/schemas/
 */

export interface ApiResponse<T> {
  status: 'success' | 'error';
  data: T;
  message?: string;
}

// --- Dashboard ---

export interface DashboardMetrics {
  total_valuation: number;
  uninvested_cash: number;
  gross_exposure: number;
  leverage_ratio: number;
  active_agents: number;
  risk_exposure: string;
  total_pnl: number;
  unrealized_pnl: number;
  roi_percentage: number;
  performance_change: string;
}

export interface PositionItem {
  ticker: string;
  name: string | null;
  quantity: number;
  avg_price: number;
  market_price: number;
  market_value: number;
  pnl: number;
  pnl_percent: number;
  weight: number;
}

export interface IntelligenceBriefing {
  executive_summary: string;
  recommendation: string;
  ai_note: string;
  observation_window: string;
  sentiment_metrics: Array<{
    label: string;
    value: number;
    trend: 'UP' | 'DOWN' | 'NEUTRAL';
  }>;
  stats?: Array<{
    title: string;
    value: string;
    change: string;
    icon: string;
  }>;
}

export interface AgentStatus {
  id: string;
  name: string;
  strategy: string;
  performance: string;
  accuracy: number;
  recommendation_count: number;
}

// --- Transactions ---

export interface TransactionRecord {
  id: string;
  ticker: string;
  action: string;
  quantity: number;
  price: number;
  fees: number;
  date: string;
}

// --- Settings ---

export interface SystemSettings {
  [key: string]: any;
}

export interface AIModel {
  id: string;
  name: string;
  provider: string;
  context_window: number;
}
