# Concurrency

| Concern | Mechanism | Code |
|---|---|---|
| Blocking drivers | Sync SQLAlchemy / pymongo calls run via `asyncio.to_thread`, so the event loop stays free | `adapters/sql.py`, `adapters/mongo.py` |
| Duplicate engines under race | `AdapterPool` uses a per-connection `asyncio.Lock` | `adapters/pool.py` |
| Engine / FD exhaustion | LRU cap (`MAX_ENGINES`), idle eviction, small pools (3, no overflow), dispose on connection delete | `adapters/pool.py` |
| Overload | `RunGuard`: global, per-user and per-connection caps return **429** | `services/run_guard.py` |
| Double submit in one chat | One active run per session returns **409**; UI disables Send | `services/run_guard.py`, `ChatWindow.tsx` |
| Slow queries | Per-query timeout, whole-run deadline, `maxTimeMS` for Mongo | `adapters/*`, `chat_service.py` |
| Client disconnect / Stop | `AbortController` closes the stream; generator `finally` releases the slot | `frontend/lib/api.ts`, `chat_service.py` |
| Message ordering | `seq = max+1` in the insert transaction with `UNIQUE(session_id, seq)` | `services/session_service.py` |
| App DB sessions | One async SQLAlchemy session per request; streaming persistence uses its own session | `deps.py`, `chat_service.py` |
| Stale slots | `RunGuard` expires entries older than deadline + 30 s | `services/run_guard.py` |

## Scaling out
State kept in process: `RunGuard`, login limiter, `AdapterPool`. The pool is safe per worker (rebuildable). Move `RunGuard` and the limiter to Redis (`SET NX EX` locks, token buckets) before running more than one worker.

## Not yet done
- Server-side cancellation of a running query on timeout/disconnect (`pg_cancel_backend`, `KILL QUERY`).
- Idempotency keys for chat POST retries.
- Load tests (Locust/k6) against a slow fake database.
