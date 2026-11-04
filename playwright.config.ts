import { defineConfig } from "@playwright/test";
import { database } from "./e2e/database";

export default defineConfig({
  testDir: "e2e",
  outputDir: "e2e/test-results",
  reporter: "list",
  workers: 1,
  globalTeardown: "./e2e/teardown.ts",
  use: { baseURL: "http://localhost:5273" },
  webServer: [
    {
      command: "uv run -m uvicorn backend.main:app --port 8100",
      url: "http://127.0.0.1:8100/api/health",
      env: { UNDERCOVER_DB: database },
    },
    {
      command: "npx vite dashboard --port 5273 --strictPort",
      url: "http://localhost:5273",
      env: { BACKEND_URL: "http://127.0.0.1:8100" },
    },
  ],
});
