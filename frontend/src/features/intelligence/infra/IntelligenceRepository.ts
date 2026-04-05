import { apiClient } from "@/lib/apiClient";
import { IIntelligenceBriefing } from "../domain/types";

// v3.3: Repository for market intelligence, retrieving background-updated data
export const IntelligenceRepository = {
  getLatest: async (): Promise<IIntelligenceBriefing> => {
    const { data } = await apiClient.get('/api/dashboard/intelligence');
    return data.data;
  }
};
