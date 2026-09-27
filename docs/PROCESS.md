# Process

`uv sync` and `npm install` at the repo root install everything, including a git pre-commit hook. `npm run dev` starts the backend and the dashboard.

`npm run check` runs every check:

- Python: ruff (lint and format), complexipy, pyright, and pytest with 80% coverage
- TypeScript: ESLint, Prettier, tsc, vitest with 80% coverage, and knip
- Playwright end-to-end tests

The pre-commit hook runs the format, lint, type and unit test checks on every commit, and CI runs `npm run check` on every push.

## Rules

- Add tests with each change. Tests never call a model; use a stub model.
- Commit after each small change you have verified.
- Run `npm run check` before you hand work over.
- Never use `git commit --no-verify`.
- Never lower a threshold, turn off a rule or exclude a file to get a green run. If a rule looks wrong, stop and ask.
- Keep `docs/STATUS.md` up to date.
- Never push.
- Write `package.json` scripts as `uv run` commands or `.mjs` files so they work on Windows.
