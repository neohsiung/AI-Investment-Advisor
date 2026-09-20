import type { NextConfig } from "next";

// BACKEND_URL is read when this config is evaluated, and Next bakes the result
// into routes-manifest.json at BUILD time — `output: 'standalone'` does not
// re-evaluate rewrites at server start. Changing it therefore needs a rebuild.
//
// That matters less than it sounds: in the Docker deployment these rewrites are
// never exercised. nginx owns the routing (infra/nginx/nginx.conf) — the browser
// talks to the gateway, which proxies /api/ and /webhook/ straight to the
// backend, so requests never reach the Next server. The rewrites exist for
// `npm run dev` against a backend on localhost:8000.
//
// If you ever bypass nginx and serve the Next container directly, pass
// --build-arg BACKEND_URL=... at image build time.
//
// rewrites 會在 build 時被寫入 routes-manifest.json，無法在啟動時變更；
// 但 Docker 部署由 nginx 負責路由，這段只在本機 `npm run dev` 時生效。
const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

// NOTE: next-pwa removed — it injected webpack config incompatible with Next.js 16 Turbopack.
// PWA support can be re-added with a Turbopack-compatible alternative (e.g. @serwist/next).

const nextConfig: NextConfig = {
  output: 'standalone',
  async rewrites() {
    return {
      // afterFiles: Next's own route handlers are matched first, and only
      // unmatched /api/* falls through to the backend proxy.
      afterFiles: [
        {
          source: '/api/:path*',
          destination: `${BACKEND_URL}/api/:path*`,
        },
        {
          source: '/webhook/:path*',
          destination: `${BACKEND_URL}/webhook/:path*`,
        },
      ],
    };
  },
};

export default nextConfig;
