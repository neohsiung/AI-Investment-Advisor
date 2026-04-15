import axios, { AxiosError, InternalAxiosRequestConfig } from "axios";

// All API calls use relative paths so they go through the Next.js proxy (next.config.ts rewrites).
// This eliminates CORS issues and ensures cookies work correctly in all environments (local, Docker, prod).
// NEVER use an absolute URL here — that bypasses the proxy and breaks cookie-based auth.
const api = axios.create({
  baseURL: "", // Relative URLs only — Next.js proxy handles routing to the backend
  withCredentials: true, // Required for HTTPOnly cookie auth
  headers: {
    "Content-Type": "application/json",
  },
});

// 請求攔截器：統一加上 Bearer Token (相容 Sprint 3 localStorage 機制)
api.interceptors.request.use((config) => {
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("access_token");
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  return config;
});

// 響應攔截器：處理 Token 過期與自動刷新
api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean };

    // Skip refresh logic if already on an auth page (prevents infinite redirect loop)
    const isOnAuthPage = typeof window !== "undefined" && window.location.pathname.startsWith("/auth");
    // Skip refresh for the /api/auth/me check itself — let useAuth handle the UI state
    const isAuthMeRequest = originalRequest.url?.includes("/api/auth/me");

    if (error.response?.status === 401 && !originalRequest._retry && !isOnAuthPage && !isAuthMeRequest) {
      originalRequest._retry = true;

      try {
        const refreshToken = localStorage.getItem("refresh_token");
        const res = await axios.post(`/api/v1/auth/refresh`, { refresh_token: refreshToken }, { withCredentials: true });
        
        if (res.data?.access_token) {
          localStorage.setItem("access_token", res.data.access_token);
          if (originalRequest.headers) {
             originalRequest.headers.Authorization = `Bearer ${res.data.access_token}`;
          }
        }
        return api(originalRequest);
      } catch (refreshError) {
        // Refresh failed — redirect to login only if not already there
        if (typeof window !== "undefined" && !window.location.pathname.startsWith("/auth")) {
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
