# Suggestions: Features and Optimizations

## Done
- **Export** results to CSV and JSON.
- **Chart picker** (bar, line, pie) with an automatic default.
- **Alembic migrations**, rotating `server.log` with request ids, dark mode, and a Spider eval runner (`backend/evals`).

## Features
- **Excel (.xlsx) export** and a scatter chart; pin charts to dashboards that refresh on a schedule.
- **Editable query**: tweak the generated SQL and re-run it (through the same validator).
- **Schema explorer** sidebar with user-written table/column descriptions that improve accuracy.
- **Follow-up suggestions** after each answer; query history search; saved/pinned questions.
- **Shareable read-only chat links**; OAuth (Google, GitHub).
- **Multiple databases per chat** and cross-database comparisons.
- **Answer critique node**: an LLM check that a corrected query still answers the original question (planned in the design, not in v1).
- **Streaming answer text** token by token.

## Reliability and performance
- Semantic cache for repeated questions; few-shot examples learned from thumbs-up answers.
- Large schemas: pick relevant tables first, then send only their DDL (retrieval over schema, not a vector DB of user data).
- Server-side query cancellation; background worker (ARQ/Celery) for very long queries.
- Redis for rate limits, run locks and schema cache across workers.
- Refresh-token rotation; per-user quotas and token-usage metering.

## Quality and operations
- Run the Spider eval in CI (a small `--sample` with a cost cap) and track accuracy and average retries over time. The measured retry benefit is small, so repeat each setting a few times before drawing conclusions.
- Observability beyond logs: OpenTelemetry and LangSmith traces of the attempt history.
- Docker Compose (api, web, postgres, redis) and CI for lint, tests and `next build`.
- Generate frontend types from the FastAPI OpenAPI schema to prevent contract drift.
- Playwright end-to-end tests for login, connect, chat, retry display.
