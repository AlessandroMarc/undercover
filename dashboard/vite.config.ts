import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Only npm run dev reads .env, from the repo root. The unit tests and the
// end-to-end tests set their own values, so the checks never read it.
const REPO_ROOT = fileURLToPath(new URL("..", import.meta.url));

export default defineConfig(({ mode }) => ({
  plugins: [react()],
  envDir: mode === "development" ? REPO_ROOT : false,
  server: {
    proxy: { "/api": process.env.UNDERCOVER_API ?? "http://127.0.0.1:8000" },
  },
  test: {
    environment: "jsdom",
    env: {
      VITE_SUPABASE_URL: "https://supabase.test",
      VITE_SUPABASE_PUBLISHABLE_KEY: "test-publishable-key",
    },
    setupFiles: ["src/setupTests.ts"],
    coverage: {
      include: ["src/**"],
      exclude: ["src/main.tsx"],
      thresholds: { statements: 80 },
    },
  },
}));
