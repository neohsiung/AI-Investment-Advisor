import { apiClient } from "@/lib/apiClient";

export const NotificationRepository = {
  archiveAll: async (): Promise<void> => {
    await apiClient.delete('/api/v1/dashboard/alerts');
  }
};
