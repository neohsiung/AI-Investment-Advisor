import axios from "axios";

/**
 * The single HTTP transport for the whole app.
 *
 * All calls use relative paths so they go through the Next.js proxy
 * (next.config.ts rewrites). NEVER use an absolute URL here — that bypasses the
 * proxy and reintroduces CORS.
 *
 * Authentication
 * --------------
 * This is a single-operator deployment. There is no login, no JWT, and no token
 * refresh: the backend resolves the owner itself (src/config/owner.py) and the
 * API is published on 127.0.0.1 only.
 *
 * The Bearer/localStorage/refresh-and-redirect machinery that used to live here
 * is gone. It depended on a Google OAuth flow that no longer exists, so it could
 * only ever have produced a redirect loop to a deleted /auth/login page.
 *
 * If you run the backend with AUTH_MODE=token (required when exposing it beyond
 * loopback), the browser has no way to hold that secret without shipping it in
 * the JS bundle — which would hand it to anyone who can load the page. So the
 * dashboard is loopback-only by design; the ngrok tunnel exposes the webhook
 * endpoints exclusively, never /api/v1.
 *
 * 單人部署：無登入、無 JWT。AUTH_MODE=token 時儀表板僅限本機使用，
 * 對外通道只開放 webhook 端點。
 */
const api = axios.create({
  baseURL: "", // Relative URLs only — the Next.js proxy routes to the backend
  withCredentials: true,
  headers: {
    "Content-Type": "application/json",
  },
});

export default api;

/** Generic SWR fetcher. */
export const fetcher = (url: string) => api.get(url).then((res) => res.data);
