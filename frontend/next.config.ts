import type { NextConfig } from "next";

// BACKEND_URL must be available at build time for rewrites().
// In Docker: set via build arg BACKEND_URL=http://mcp_server:8000
// In local dev: defaults to http://localhost:8000
const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

const nextConfig: NextConfig = {
  output: 'standalone',
  async rewrites() {
    return {
      // beforeFiles rewrites run before checking pages/API routes.
      // We use afterFiles so internal Next.js API routes (like /api/auth/set-session) 
      // are checked FIRST and only fall through to the proxy if not found.
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
