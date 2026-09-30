# Tech stack

- `backend/`: FastAPI and SQLite. Every API operation has an `operation_id`, a one-line docstring and no optional inputs. Paying a claim is a separate operation that takes the amount.
- `agent/`: LangChain's `create_agent` on OpenRouter, in three parts. `api.py` is the only way the agent reaches the backend: claims, runs, its instructions and the documents. `tools.py` holds every tool, and each tool reads what it needs, such as the claim a claim agent is working on, from the agent's `context_schema` through `ToolRuntime`. `harness.py` builds and runs the agents: `run_queue(cap, llm, claim_llm)` runs a queue agent that hands each claim to a claim agent, and `work_claim(claim_id, agent)` works one claim from a clean start, keeping no checkpoints. LangChain middleware records each reply, tool call, tool result and section read on the claim, returns refusals to the model and limits the model calls. The to-do list, the subagent and the document lookup are our own tools, with no other agent framework. It uses `deepseek/deepseek-v4.1-flash` with low reasoning effort by default, or the model in the environment variable `MODEL_NAME` if set, such as `openrouter/free`. The backend's address is `UNDERCOVER_API` in the environment, not `.env`, as for the dashboard, or `http://127.0.0.1:8000`.
- `dashboard/`: React, Vite and TypeScript.
- `e2e/`: Playwright tests.
- `data/`: the business data the backend starts from. The agent never sees `data/evals/`, which holds the answer key.

Python 3.12 with uv, all in the root `pyproject.toml`. Node 26. The OpenRouter key is `OPENROUTER_API_KEY` in `.env`.
