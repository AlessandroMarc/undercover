import { tmpdir } from "node:os";
import { join } from "node:path";

// A database of its own for each run, so the tests start from the seed data.
export const database = join(
  tmpdir(),
  `undercover-e2e-${String(process.pid)}.db`,
);
