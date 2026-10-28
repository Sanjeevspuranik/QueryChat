# API and Data Model

All routes are under `/api`. Auth is an httpOnly, SameSite=Lax cookie (`access_token`). Errors are `{"detail": "..."}`.

| Method | Path | Purpose | Errors |
|---|---|---|---|
| POST | `/auth/register` | Create account, sets cookie | 409 duplicate |
| POST | `/auth/login` | Sign in | 401, 429 throttled |
| POST | `/auth/logout` | Clear cookie | |
| GET | `/auth/me` | Current user | 401 |
| POST | `/connections/test` | Validate URL, connect, preview schema | 400 |
| POST | `/connections` | Save connection (URL encrypted) | 400 |
| GET | `/connections` | List (URL never returned) | |
| GET | `/connections/{id}/schema` | Structured schema (tables, columns, PK/FK) for the explorer | 404 |
| DELETE | `/connections/{id}` | Delete with its chats | 404 |
| POST | `/sessions` | New chat for a connection | 404 |
| GET | `/sessions` | List chats | |
| GET | `/sessions/{id}` | Chat with messages | 404 |
| DELETE | `/sessions/{id}` | Delete chat | 404 |
| GET | `/sessions/{id}/messages/{mid}/export?format=csv\|json` | Download a stored result as a file (no query re-run; CSV neutralises spreadsheet formulas) | 400 format, 404 |
| POST | `/sessions/{id}/chat` | Ask a question, **SSE stream** | 404, 409 busy, 429 limits |
| GET | `/health` | Liveness | |

## SSE events (`data: <json>\n\n`)
```
{"type":"status","message":"..."}
{"type":"query","query":"..."}
{"type":"attempt_failed","n":1,"stage":"execution","error":"..."}
{"type":"retrying","retry":1,"max_retries":3,"message":"Fixing query (retry 1 of 3)"}
{"type":"done","message":{ ...Message }}        // always the last event
```
Failures that end a run still finish with `done` and `status: "failed"`, so the UI has one terminal path.

## Message
`{id, seq, role, content, query, result:{columns,rows,row_count,truncated}, attempts[], status, created_at}`

## Tables
- `users(id, email unique, password_hash)`
- `connections(id, user_id, name, db_type, url_encrypted)`
- `chat_sessions(id, user_id, connection_id, title)`
- `messages(id, session_id, seq, role, content, query, result_json, attempts_json, status)`; `UNIQUE(session_id, seq)`

Every read and write is scoped by `user_id`; a foreign id returns 404 (no existence leak).

## Database URLs
| Database | Example (SQLAlchemy driver must be installed) |
|---|---|
| SQLite | `sqlite:///./chinook.db` |
| PostgreSQL | `postgresql+psycopg://user:pass@host:5432/db` |
| MySQL | `mysql+pymysql://user:pass@host:3306/db` |
| SQL Server | `mssql+pyodbc://user:pass@host/db?driver=ODBC+Driver+18+for+SQL+Server` |
| MongoDB | `mongodb://user:pass@host:27017/db` or `mongodb+srv://...` |

Any other SQLAlchemy URL works without code changes. Vector-store schemes and hosts are rejected.
