# Security

| Risk | Control | Code |
|---|---|---|
| LLM emits writes / DDL | 3 layers: sqlglot AST allows one `SELECT`/`WITH` and rejects write nodes; Mongo stage allowlist and forbidden-operator scan; session set read-only at the database (SQLite `query_only`, Postgres / MySQL read-only transaction mode) | `adapters/sql.py`, `adapters/mongo.py` |
| "Fixing" into a write | Retries go through the same validator; security violations are never retried | `agent/nodes.py` |
| Credential leak | URLs Fernet-encrypted at rest, never returned by the API, stripped from driver errors before logs or the LLM | `core/security.py`, `adapters/base.py` |
| SSRF / local files | `UrlPolicy` blocks non-global IPs and restricts SQLite to `SQLITE_ALLOWED_DIR` when `ALLOW_PRIVATE_HOSTS=false` | `adapters/url_policy.py` |
| Vector stores | Denied by scheme and host keywords | `adapters/url_policy.py` |
| Account takeover | argon2 hashes, JWT in httpOnly SameSite=Lax cookie, generic login error, login throttling | `services/auth_service.py`, `routers/auth.py` |
| IDOR | All lookups scoped by `user_id`; 404 on foreign ids | `services/*` |
| CSRF | SameSite=Lax cookie plus JSON-only bodies; CORS restricted to configured origins | `main.py` |
| Resource abuse | Row cap, query timeout, run deadline, RunGuard limits, engine LRU cap | see [concurrency.md](./concurrency.md) |
| Input abuse | Pydantic length limits on every body | `schemas.py` |

## Deployment checklist
- Generate real `SECRET_KEY` and `ENCRYPTION_KEY` (`python scripts/gen_keys.py`); never commit `.env`.
- Set `COOKIE_SECURE=true` behind HTTPS and `ALLOW_PRIVATE_HOSTS=false` for any hosted multi-tenant setup.
- Tell users to supply a **read-only database account**; app-level checks are defence in depth, not a substitute.
- Rotate any API key that has ever been committed (check the repo-root `.env`).
- Losing `ENCRYPTION_KEY` makes saved connections unreadable; back it up.
- Data sent to the LLM: schema, question, recent chat text, and up to 20 result rows for summarization.
