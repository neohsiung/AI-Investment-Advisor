import { apiClient } from "@/lib/apiClient";
import { IPortfolioSummary, IPosition } from "../domain/types";

// v3.3: Repository Pattern to decouple UI from API endpoint structure
export const PortfolioRepository = {
  getSummary: async (): Promise<IPortfolioSummary> => {
    const { data } = await apiClient.get('/api/v1/dashboard/summary');
    // Ensure we handle standard API response wrapper (e.g. { data: { ... } })
    return data.data || data;
  },
  
  getPositions: async (): Promise<IPosition[]> => {
    const { data } = await apiClient.get('/api/v1/dashboard/positions');
    return data.data || data || [];
  },

  rebalance: async (): Promise<void> => {
    await apiClient.post('/api/v1/dashboard/rebalance');
  },

  generateReport: async (): Promise<void> => {
    await apiClient.post('/api/v1/dashboard/report');
  },

  getPerformanceHistory: async (): Promise<any[]> => {
    const { data } = await apiClient.get('/api/v1/dashboard/performance/history');
    return data.data || data || [];
  }
};
