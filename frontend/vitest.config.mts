import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Test setup for the dashboard (2026-08-14). Before this, 79 .ts/.tsx files had
// zero tests — and this is the surface a human reads before approving a trade.
// jsdom rather than a browser runner: what is worth pinning here is render
// output and data-shape handling, not layout.
// `.mts` so the config is loaded as ESM; `resolve.tsconfigPaths` is Vite's
// native replacement for the vite-tsconfig-paths plugin and resolves `@/*`
// from tsconfig.json, so the alias cannot drift from the app's.
// 儀表板原本 79 個檔案 0 測試，而這正是人類按下核准前所看的介面。
export default defineConfig({
  plugins: [react()],
  resolve: { tsconfigPaths: true },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    css: false,
    restoreMocks: true,
  },
});
