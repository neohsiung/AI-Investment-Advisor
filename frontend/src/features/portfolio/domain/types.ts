export interface IPortfolioSummary {
  total_valuation: number;
  uninvested_cash: number;
  leverage_ratio: number;
  roi_percentage: number;
  total_pnl: number;
  risk_exposure: string;
}

export interface IPosition {
  ticker: string;
  name?: string;
  quantity: number;
  avg_price: number;
  current_price: number;
  market_value: number;
  pnl: number;
  pnl_percent: number;
  weight: number;
}
