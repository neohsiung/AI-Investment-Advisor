import axios, { AxiosError, InternalAxiosRequestConfig } from "axios";

// 後端 API 基礎路徑
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const api = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: true, // 重要：確保跨域請求攜帶 HTTPOnly Cookies
  headers: {
    "Content-Type": "application/json",
  },
});

// 響應攔截器：處理 Token 過期與自動刷新
api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean };

    // 如果返回 401 且尚未重試過
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;

      try {
        // 呼叫後端的 refresh 端點
        // 注意：refresh 端點本身也會讀取 refresh_token cookie 並設置新的 access_token cookie
        await axios.post(`${API_BASE_URL}/api/auth/refresh`, {}, { withCredentials: true });
        
        // 刷新成功後重新執行原請求
        return api(originalRequest);
      } catch (refreshError) {
        // 刷新失敗 (例如 Refresh Token 也過期了)，重定向到登入頁
        if (typeof window !== "undefined") {
          window.location.href = `/auth/login?reason=session_expired`;
        }
        return Promise.reject(refreshError);
      }
    }

    return Promise.reject(error);
  }
);

export default api;

/**
 * 通用的 SWR Fetcher
 */
export const fetcher = (url: string) => api.get(url).then((res) => res.data);
