import axios from "axios";

// v3.1: Centralized API Client with standard Interceptors
export const apiClient = axios.create({
  baseURL: "/", // Proxied via Next.js to the backend
  headers: {
    "Content-Type": "application/json",
  },
});

// Request Interceptor (e.g. for Auth tokens if managed client-side)
apiClient.interceptors.request.use(
  (config) => {
    // In this app, auth is mainly handled via HttpOnly cookies by the proxy,
    // but we can add JWT here if needed in the future.
    return config;
  },
  (error) => Promise.reject(error)
);

// Response Interceptor for global error handling
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    console.error("API Error:", error.response?.data || error.message);
    // Handle 401/403 globally if needed
    return Promise.reject(error);
  }
);
