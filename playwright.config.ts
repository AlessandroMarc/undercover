import { defineConfig } from "@playwright/test";

// The tests run their own backend and dashboard, on their own ports and
// database, so they never touch the servers started by `npm run dev`.
export default defineConfig({
  testDir: "e2e",
  outputDir: "e2e/test-results",
  reporter: "list",
  use: { baseURL: "http://localhost:5174" },
  webServer: [
    {
      command:
        "uv run -m backend.seed && uv run uvicorn backend.main:app --port 8001",
      url: "http://127.0.0.1:8001/api/health",
      env: { UNDERCOVER_DB: "e2e/undercover.db" },
    },
    {
      command: "npx vite dashboard --port 5174 --strictPort",
      url: "http://localhost:5174",
      env: { UNDERCOVER_API: "http://127.0.0.1:8001" },
    },
  ],
});
