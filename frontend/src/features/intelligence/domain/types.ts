export interface ISentimentMetric {
  label: string;
  value: number;
  color: string;
}

export interface IIntelligenceBriefing {
  executive_summary: string;
  recommendation: string;
  ai_note: string;
  observation_window: string;
  sentiment_metrics: ISentimentMetric[];
}
