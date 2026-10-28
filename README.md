# 📊 QueryChat: Chat with Any Database

QueryChat turns plain-English questions into safe, read-only database queries, runs them, and shows the answer as text, a table or a chart. It is a **FastAPI + Next.js** application with login, saved chat sessions, and a **self-correcting agent** that retries failed queries (up to 3 times) before giving up.

Connect SQLite, PostgreSQL, MySQL, SQL Server, MongoDB and other non-vector databases through **one URL field**.

---

## 🎥 Watch the Demo

**[▶ Watch the demo of the current FastAPI + Next.js app](demo/QueryChat_demo.mp4)** (2:14). GitHub plays the file in the browser once you open it.

<details>
<summary>Original Streamlit demo</summary>

<video src="https://github.com/user-attachments/assets/47841152-1b70-4bbe-98fc-d0ea1c0f8023" controls="controls" style="max-width: 100%;">
  Your browser does not support the video tag.
</video>

_If the video does not load, [view it directly here](https://github.com/user-attachments/assets/47841152-1b70-4bbe-98fc-d0ea1c0f8023)._

</details>

---

## ✨ Features

**Chat and results**
- Ask in plain English; follow-up questions use the earlier turns, including the SQL that was run.
- Answers are rendered as **Markdown**, with the generated query and the attempt trace in a collapsible block.
- Results show as a **table** or a **bar, line or pie chart**, with pickers for the label and value columns.
- **Export** any result as CSV or JSON. CSV is Excel-safe (BOM, and cells that start with `=`, `+`, `-` or `@` are neutralised).
- **Dark and light themes**, following your system setting until you choose one.
- Streaming progress, a **Stop** button, and partial results saved if you cancel.

**Agent**
- Graph-structured loop: `load schema → generate → validate → execute → summarize`, with a **retry gate** (default 3, ceiling 5) that feeds the error back to the model.
- Retries parse errors, execution errors, duplicate queries and one empty-result case. It does **not** retry security violations, connection errors or schema failures.
- Works with reasoning models (e.g. `gpt-6-luna`) and classic models: `temperature=0` is sent only where the model accepts it.

**Databases**
- SQL through SQLAlchemy (SQLite, PostgreSQL, MySQL/MariaDB, SQL Server, Oracle) and MongoDB through a dedicated adapter.
- Connection URLs are encrypted at rest and never logged or returned by the API.
- A new adapter is one class plus one registry entry.

**Accounts and operations**
- Register and login with Argon2 password hashes and JWT in an HTTP-only cookie.
- Chat sessions, messages and connections are stored per user.
- Alembic migrations run automatically at startup.
- Rotating `server.log` with a request id on every line.
- Per-connection concurrency limits and timeouts so one user can't exhaust a database.

---

## 🏗 Architecture

![Architecture](architecture/architecture.svg)

```text
Browser (Next.js, React)
   │  /api/*  (proxied by Next rewrites, cookie auth, SSE for chat)
   ▼
FastAPI  ── routers ──► services ──► agent (LangGraph) ──► adapters ──► user databases
                           │                 │
                           │                 └─► OpenAI (SQL generation and summary)
                           └─► app database (SQLite/Postgres via SQLAlchemy + Alembic)
```

| Layer | Folder | Responsibility |
| --- | --- | --- |
| Routers | `backend/app/routers` | HTTP only: validation, auth dependency, status codes |
| Services | `backend/app/services` | Business logic: auth, connections, sessions, chat runs, export, `QueryRunner`, `RunGuard` |
| Agent | `backend/app/agent` | LangGraph state, nodes, LLM wrapper, events |
| Adapters | `backend/app/adapters` | One class per database family behind a common interface, URL policy, SQLite path resolver, pooling |
| Core | `backend/app/core` | Settings, security (hashing, JWT, encryption), errors, logging |
| DB | `backend/app/db` | App models and Alembic bootstrap |

### Agentic graph

```mermaid
flowchart TD
    S([Start]) --> LS[load_schema]
    LS -->|schema ok| G[generate<br/>LLM writes the query]
    LS -->|schema failed| F[fail<br/>explain the last problem]
    G --> V[validate<br/>sqlglot AST / Mongo allowlist]
    V -->|valid| E[execute<br/>read-only, timeout, row cap]
    V -->|invalid or unsafe| RG{retry_gate}
    E -->|rows returned| SUM[summarize<br/>short answer]
    E -->|error, duplicate, empty once| RG
    RG -->|retryable and retry_count < max_retries| G
    RG -->|exhausted or non-retryable| F
    SUM --> X([END])
    F --> X

    classDef llm fill:#e0e7ff,stroke:#4f46e5,color:#1c1e2b;
    classDef guard fill:#fef3c7,stroke:#d97706,color:#1c1e2b;
    classDef bad fill:#fee2e2,stroke:#c0262d,color:#1c1e2b;
    class G,SUM llm;
    class V,RG guard;
    class F bad;
```

Blue nodes call the LLM, amber nodes are deterministic guards, and red is the failure exit. Each correction feeds the error and every earlier failed query back into `generate`, up to `AGENT_MAX_RETRIES` (default 3).

1. **Load schema:** a structured `SchemaInfo` (tables, columns, keys) is read once and rendered into the prompt.
2. **Generate:** the model writes one query, using recent history and the schema.
3. **Validate:** SQL is parsed with `sqlglot` and must be a single `SELECT` or `WITH`. Mongo pipelines are checked against a stage allowlist.
4. **Execute:** runs read-only with a timeout and row cap.
5. **Summarize:** a fast model writes a short answer. Failed attempts are recorded in the message so the UI can show them.

More detail: [agent-flow.md](architecture/agent-flow.md), [architecture.md](architecture/architecture.md), [concurrency.md](architecture/concurrency.md).

### Security

| Risk | Control |
| --- | --- |
| LLM emits writes or DDL | AST allowlist, Mongo operator scan, and a read-only session at the database (SQLite `mode=ro` and `query_only`, Postgres/MySQL read-only transactions) |
| SSRF or local file access | `UrlPolicy` blocks non-public IPs and restricts SQLite paths when `ALLOW_PRIVATE_HOSTS=false` |
| Credential leak | Connection URLs encrypted with Fernet; never logged or returned |
| Account abuse | Argon2id hashing, HTTP-only cookie, per-user ownership checks on every resource |
| CSV injection | Formula characters neutralised on export |

Full table: [security.md](architecture/security.md). Run the app with `ALLOW_PRIVATE_HOSTS=false` if it is hosted for others.

---

## 📂 Project Structure

```text
QueryChat/
├── backend/
│   ├── app/                 # FastAPI app (routers, services, agent, adapters, core, db)
│   ├── alembic/             # Migrations (0001_initial)
│   ├── evals/               # Spider benchmark runner and scoring
│   ├── scripts/gen_keys.py  # Generates SECRET_KEY and ENCRYPTION_KEY
│   ├── tests/               # pytest suite
│   ├── logs/                # server.log (git-ignored)
│   ├── .env.example
│   └── requirements.txt
├── frontend/                # Next.js (App Router, TypeScript, Recharts)
│   └── src/{app,components,hooks,lib}
├── architecture/            # Design docs, API reference, security, suggestions
├── demo/QueryChat_demo.mp4  # Demo video (compressed, 2:14)
├── app.py, graph.py         # Original Streamlit version (legacy)
└── README.md
```

---

## ⚙️ Setup

**Requirements:** Python 3.12 (the version it is developed and tested on), Node.js 18+, an OpenAI API key.

### 1. Backend (http://localhost:8000)

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env            # macOS/Linux: cp .env.example .env
python scripts/gen_keys.py        # paste the two keys into .env
uvicorn app.main:get_app --factory --reload --port 8000
```

Set `OPENAI_API_KEY` in `.env`. Install a driver only for the databases you use:

| Database | Driver |
| --- | --- |
| PostgreSQL | `pip install "psycopg[binary]"` |
| MySQL / MariaDB | `pip install pymysql` |
| SQL Server | `pip install pyodbc` |
| Oracle | `pip install oracledb` |
| SQLite, MongoDB | included |

### 2. Frontend (http://localhost:3000)

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000, register, add a database, and start chatting. Chat is ready as soon as a database is added.

### Configuration (`backend/.env`)

| Setting | Default | Purpose |
| --- | --- | --- |
| `SECRET_KEY`, `ENCRYPTION_KEY` | none | JWT signing and connection-URL encryption (generate with `scripts/gen_keys.py`) |
| `APP_DATABASE_URL` | `sqlite+aiosqlite:///./querychat.db` | The app's own database (relative paths resolve inside `backend/`) |
| `DB_BOOTSTRAP` | `migrate` | `migrate` runs Alembic at startup; `create_all` is for throwaway DBs |
| `OPENAI_API_KEY` | none | LLM access |
| `LLM_MODEL`, `LLM_FAST_MODEL` | `gpt-4o-mini` | Query model and summary model |
| `AGENT_MAX_RETRIES` | `3` | Self-correction attempts (ceiling 5) |
| `ALLOW_PRIVATE_HOSTS` | `true` | Set `false` when hosting for others |
| `SQLITE_ALLOWED_DIR` | empty | Restricts SQLite files when private hosts are blocked |
| `CORS_ORIGINS`, `COOKIE_SECURE` | localhost, `false` | Set `COOKIE_SECURE=true` behind HTTPS |
| `LOG_LEVEL`, `LOG_TO_FILE`, `LOG_DIR`, `LOG_MAX_MB`, `LOG_BACKUPS` | `INFO`, `true`, `backend/logs`, `5`, `5` | Logging |

---

## 🔌 Connecting a Database

Paste one URL into **Add database** and press **Test**, then **Save**.

| Database | Example URL |
| --- | --- |
| SQLite | `sqlite:///C:/data/chinook.db` |
| PostgreSQL | `postgresql://user:pass@host:5432/dbname` |
| MySQL | `mysql://user:pass@host:3306/dbname` |
| SQL Server | `mssql://user:pass@host:1433/dbname` |
| MongoDB | `mongodb://user:pass@host:27017/dbname` |

**SQLite notes:** use an absolute path (backslashes and quotes are tolerated). Relative paths resolve against the folder the backend runs in. Files are opened read-only, and a missing file gives a clear error instead of creating an empty database.

Use a **read-only database user** where you can. The app also enforces read-only access, as a second layer.

---

## 🔍 Logs

`backend/logs/server.log` rotates at `LOG_MAX_MB` and keeps `LOG_BACKUPS` files.

```text
2026-10-29 00:49:29,450 INFO querychat.chat   [b311273302c9] run start session=... question_chars=47 history=0
2026-10-29 00:49:35,617 INFO querychat.chat   [b311273302c9] run end session=... status=ok attempts=1 rows=2 ms=6156
2026-10-29 00:49:35,644 INFO querychat.access [c8dbb41d1616] GET /api/sessions -> 200 (7 ms)
```

Every response carries an `X-Request-ID` header, and an unexpected 500 returns that id, so any error can be found in the log. URLs, passwords and question text are never logged.

---

## 🔌 API

All routes are under `/api` and need the login cookie except register and login. Full reference: [api.md](architecture/api.md).

| Area | Routes |
| --- | --- |
| Auth | `POST /auth/register`, `POST /auth/login`, `POST /auth/logout`, `GET /auth/me` |
| Connections | `POST /connections/test`, `POST /connections`, `GET /connections`, `GET /connections/{id}/schema`, `DELETE /connections/{id}` |
| Sessions | `POST /sessions`, `GET /sessions`, `GET /sessions/{id}`, `DELETE /sessions/{id}` |
| Chat | `POST /sessions/{id}/chat` (server-sent events) |
| Export | `GET /sessions/{id}/messages/{message_id}/export?format=csv\|json` |

---

## 🧪 Testing and Evaluation

```bash
cd backend
python -m pytest -q                      # unit and API tests (73)
cd ../frontend
npx tsc --noEmit && npm run build        # typecheck and production build
```

**Spider benchmark.** `evals/run_spider.py` measures execution accuracy on the [Spider](https://yale-lily.github.io/spider) dev set (1,034 questions, 20 databases). It uses the app's own agent and validator, and scores results order-insensitively unless the gold SQL has `ORDER BY`.

```bash
cd backend
# Validate the gold SQL only, with no LLM calls
python -m evals.run_spider --data <path-to>\spider_data --gold-check

# Cheap sample: 40 questions, no retries
python -m evals.run_spider --data <path-to>\spider_data --sample 40 --max-retries 0 --concurrency 4 --max-cost 0.25

# Full run with self-correction
python -m evals.run_spider --data <path-to>\spider_data --sample 0 --max-retries 3 --concurrency 6 --max-cost 1
```

`--data` is the folder that contains `database/` and `dev.json`. Results go to `backend/evals/results/` as JSONL, with accuracy by category and database, tokens, and cost. Evals measure generation only, so no summary calls are made.

### 📈 Results on a Spider subset: with and without self-correction

Run: every dev question from six Spider databases (`battle_death`, `course_teach`, `network_1`, `real_estate_properties`, `tvshow`, `voter_1`), 183 questions, with `gpt-6-luna`. The same questions were run twice, once with a single attempt and once with up to 3 correction retries.

```bash
python -m evals.run_spider --data <path-to>\spider_data --sample 0 --db voter_1 tvshow battle_death course_teach network_1 real_estate_properties --max-retries 0 --concurrency 4 --out evals\results\spider_hard_retries0.jsonl
python -m evals.run_spider --data <path-to>\spider_data --sample 0 --db voter_1 tvshow battle_death course_teach network_1 real_estate_properties --max-retries 3 --concurrency 4 --out evals\results\spider_hard_retries3.jsonl
```

| Metric | No retries | Self-correction (3 retries) |
| --- | --- | --- |
| Questions | 183 | 183 |
| **Execution accuracy** | **138 / 183 = 75.4%** | **149 / 183 = 81.4%** |
| Attempts per question | 183 × 1 | 173 × 1, 10 × 2 |
| Median latency | 2.1 s | 2.3 s |
| Tokens in / out | 30,486 / 19,996 (12,788 reasoning) | 33,201 / 24,516 (16,775 reasoning) |
| Average tokens per question | 276 | 315 |
| Total cost | $0.0252 | $0.0289 |

**By query type**

| Category | No retries | Self-correction |
| --- | --- | --- |
| simple | 67 / 79 (85%) | 72 / 79 (91%) |
| group | 19 / 26 (73%) | 20 / 26 (77%) |
| join | 34 / 50 (68%) | 35 / 50 (70%) |
| set_op | 10 / 18 (56%) | 14 / 18 (78%) |
| subquery | 8 / 10 (80%) | 8 / 10 (80%) |

**By database**

| Database | No retries | Self-correction |
| --- | --- | --- |
| tvshow | 51 / 62 (82%) | 55 / 62 (89%) |
| battle_death | 13 / 16 (81%) | 13 / 16 (81%) |
| course_teach | 24 / 30 (80%) | 24 / 30 (80%) |
| network_1 | 38 / 56 (68%) | 43 / 56 (77%) |
| real_estate_properties | 3 / 4 (75%) | 3 / 4 (75%) |
| voter_1 | 9 / 15 (60%) | 11 / 15 (73%) |

**How to read it**
- Accuracy is **execution accuracy**: the predicted query's result set is compared with the gold query's result set, so different but equivalent SQL counts as correct.
- Retries cost about 15% more tokens ($0.004 extra here). 10 questions were retried, all because the first query returned no rows. Of those, 7 ended correct.
- Comparing the two runs question by question: 135 were right in both, 31 wrong in both, 14 changed from wrong to right and 3 from right to wrong.
- **Most of the 6-point gap is run-to-run noise.** Only 4 of the net +11 came from the 10 retried questions. The other 173 were never retried, yet 10 improved and 3 got worse, because the model doesn't give the same SQL on every run. A fair estimate of the retry benefit is about +2 points, from a single run per setting.
- The retry gate reacts to errors and empty results. It can't fix a query that runs, returns rows, and is wrong, which is probably the case for most of the 31 questions wrong in both runs.
- Several misses come from Spider's gold labels, not the model. Examples: a case-sensitive `!=` on a lowercase literal, `LIMIT 1` where the question allows ties, and an inner join where a left join is arguably more complete. The real accuracy is probably higher than reported.
- The gold SQL itself was checked separately: all 1,034 dev queries pass the validator, and 1,032 of 1,034 reproduce their own results (99.8%).

An earlier 40-question stratified sample (`--sample 40 --max-retries 0`) scored 32 / 40 = 80.0% for $0.0065.

The full 1,034-question run is not done yet:

```bash
python -m evals.run_spider --data <path-to>\spider_data --sample 0 --max-retries 3 --concurrency 6 --max-cost 1
```

### Example questions to try

- *"Which artist has the most tracks?"* (the Chinook sample database, if you have it)
- *"Show total revenue by country as a chart."*
- *"For each room, show bookings, total nights and revenue, ordered by revenue."* (Spider `inn_1`)
- *"Now only the King beds."* (a follow-up that relies on chat history)

---

## 🧠 Tech Stack

| Component | Technology |
| --- | --- |
| API | [FastAPI](https://fastapi.tiangolo.com), Pydantic v2, Uvicorn |
| Agent | [LangGraph](https://github.com/langchain-ai/langgraph), [LangChain](https://github.com/langchain-ai/langchain) OpenAI |
| SQL safety | [sqlglot](https://github.com/tobymao/sqlglot) AST validation |
| Data | SQLAlchemy 2 (async), Alembic, PyMongo, SQLite by default for the app DB |
| Auth | Argon2, PyJWT, Fernet (`cryptography`) |
| Frontend | Next.js (App Router), React, TypeScript, [Recharts](https://recharts.org), react-markdown |
| Tests | pytest, pytest-asyncio, httpx |

---

## 🗺 Roadmap and Suggestions

Done: multi-database connections, auth and sessions, self-correcting agent, Alembic, structured schema, `QueryRunner`, persist-on-cancel, CSV/JSON export, chart picker, dark mode, logging, Spider eval.

Next, in rough order:

1. Editable generated query, schema explorer with column descriptions, saved questions and history search.
2. Dashboards that re-run on open and refresh on a schedule, and read-only share links.
3. Answer critique step, token streaming, OAuth (Google, GitHub).
4. Multi-database questions combined with DuckDB.
5. Redis for rate limits and caches, a background worker for long queries, Docker Compose, CI.

The full list, with reliability and operations ideas, is in [suggestions.md](architecture/suggestions.md).

---

## 🕰 Legacy Streamlit version

`app.py` and `graph.py` are the original single-user app: a LangGraph pipeline (generate SQL → execute → summarize) over a Chinook SQLite database (`chinook.db`, no longer bundled in the repo), with a Streamlit chat UI. They are kept for reference.

```bash
pip install streamlit langgraph langchain-openai sqlalchemy
# .env: OPENAI_API_KEY=... and DATABASE_URL=sqlite:///chinook.db
streamlit run app.py
```

---

## 📄 License

Released under the [GNU General Public License v3.0](LICENSE).

---

*Built for structured NL-to-SQL experimentation and agentic AI research.* 🚀
