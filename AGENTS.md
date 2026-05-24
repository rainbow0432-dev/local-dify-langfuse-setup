# Project: dify2

Langfuse-traced chat CLI backed by Dify, mem0 (Qdrant), and SQLite.

## Accounts & Secrets

All credentials live in `.env` (gitignored). Key entries:

| Service | Variable | Location |
|---|---|---|
| Langfuse UI | `http://localhost:3000` | `.env` → `LANGFUSE_PORT` |
| Langfuse API keys | `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` | `.env` |
| Langfuse login | `lym.buaa@icloud.com` / `.env` | Org: `dify2`, Project: `chat-traces` |
| Dify admin | `DIFY_ADMIN_EMAIL`, `DIFY_ADMIN_PASSWORD` | `.env` |
| DeepSeek API | `DEEPSEEK_API_KEY` | `.env` |
| Dify app | `DIFY_APP_ID`, `DIFY_API_KEY` | `.env` + `.dify-credentials` |
| mem0 API | `http://localhost:8888` | `.env` → `MEM0_PORT` |
| SQLite API | `http://localhost:8090` | `.env` → `SQLITE_API_PORT` |
| Ollama (embeddings) | `http://localhost:11434` | Local daemon, model: `nomic-embed-text` |

## Stack

- **Dify v1.13.3** — LLM orchestration (10 containers in `dify-docker/`)
- **mem0** — memory service backed by Qdrant (custom `services/mem0/main.py`)
- **Qdrant** — vector store for mem0 (replaces pgvector, no network needed)
- **Ollama** — local embedding model (`nomic-embed-text`, 768 dims)
- **SQLite API** — answer persistence (reuses mem0 image for fastapi/uvicorn)
- **Langfuse v3** — observability (6-service stack)

## Conventions

- Python: use `uv` for all package management
- Docker Compose runs from `dify-docker/` with overlay: `docker compose -f docker-compose.yaml -f ../docker-compose.override.yml`
- When model is required, stick with DeepSeek

## Architecture

```
chat.py (CLI, @observe traced)
  ├── retrieve_memories() → mem0 API (:8888)
  ├── ask_agent()         → Dify API (:80)
  ├── save_memory()       → mem0 API (:8888)
  └── save_answer()       → SQLite API (:8090)

All traces → Langfuse (:3000)
```

---

## Dify + DeepSeek Setup

### LLM Provider (DeepSeek)

Dify v1.13.3 uses a plugin system for model providers. The DeepSeek plugin is installed from the Dify marketplace.

**Plugin**: `langgenius/deepseek:0.0.15`

**Models available** (via the plugin):
| Model | Context | Notes |
|---|---|---|
| `deepseek-chat` | 1M tokens | Default chat model, supports tool-call |
| `deepseek-reasoner` | 1M tokens | Chain-of-thought reasoning |
| `deepseek-coder` | 128K tokens | Code-specialized |
| `deepseek-v4-flash` | 1M tokens | Fast, cheap |
| `deepseek-v4-pro` | 1M tokens | Premium |

**How the plugin was installed**:
1. Plugin daemon signature enforcement was disabled (`FORCE_VERIFYING_SIGNATURE=false`, `ENFORCE_LANGGENIUS_PLUGIN_SIGNATURES=false` in `dify-docker/.env`)
2. Plugin installed via marketplace API: `POST /console/api/workspaces/current/plugin/install/marketplace`
3. DeepSeek API key configured: `POST /console/api/workspaces/current/model-providers/deepseek/credentials` with `{"credentials": {"api_key": "..."}}`

**App configuration**:
- App ID: `390bdd58-bc95-44b0-bbc0-304cb7535459`
- Mode: `agent-chat` (ReAct strategy)
- Model: `langgenius/deepseek/deepseek` → `deepseek-chat`
- API key: stored in `.dify-credentials` as `DIFY_APP_API_KEY`
- Tools: 19 enabled (12 mem0ai + 7 SQLite)
- Agent-chat apps only support streaming mode (not blocking)

### Console API Authentication

The Dify Console API (under `/console/api/...`) requires **cookie-based auth** — not bearer tokens. The login endpoint encrypts credentials before sending, so raw `curl` login is impractical. The practical approach is **login via browser, then extract cookies**.

**Two types of API access**:
| API | Auth | Example |
|---|---|---|
| **App API** (`/v1/...`) | `Authorization: Bearer <DIFY_APP_API_KEY>` | `.dify-credentials` file |
| **Console API** (`/console/api/...`) | Cookie + CSRF header (see below) | Managing plugins, models, tools |

**How to extract a valid Console API token**:

1. **Login via browser**: Navigate to `http://localhost/install` or `http://localhost/signin`. Use the admin credentials from `.env`.

2. **Extract cookies**: Open browser DevTools → Application → Cookies, or use Playwright:
   ```javascript
   // Playwright — extract all auth cookies
   const cookies = await page.context().cookies();
   const cookieStr = cookies.map(c => `${c.name}=${c.value}`).join('; ');
   // Returns: "csrf_token=<JWT>; access_token=<JWT>; refresh_token=<JWT>"
   ```

3. **Use in curl**: Both the `csrf_token` cookie AND the `X-CSRF-Token` header are required:
   ```bash
   # Variables extracted from browser cookies
   CSRF_TOKEN="<value of csrf_token cookie>"
   COOKIES="csrf_token=$CSRF_TOKEN; access_token=<value>; refresh_token=<value>"

   # Example: list agent app tools
   curl -s "http://localhost/console/api/apps/<APP_ID>" \
     -H "X-CSRF-Token: $CSRF_TOKEN" \
     -b "$COOKIES" | python3 -m json.tool
   ```

**Token details**:
| Cookie | Purpose | Lifetime |
|---|---|---|
| `csrf_token` | JWT for CSRF protection — must be sent as both cookie AND `X-CSRF-Token` header | ~hours |
| `access_token` | Console API session token | ~hours |
| `refresh_token` | Used by the UI to refresh `access_token` | Longer-lived |

**Key pitfall**: The `POST /console/api/login` endpoint requires encrypted credentials (RSA + AES), not plain JSON. Attempting `{"email":"...","password":"..."}` returns `{"code":"authentication_failed","message":"Invalid encrypted data"}`. Always login through the browser UI instead.

**Key pitfall**: The `/v1/chat-messages` endpoint (App API) uses a **different** auth mechanism — just the `DIFY_APP_API_KEY` from `.dify-credentials` as a `Bearer` token. No cookies needed.

**Key pitfall**: Docker Desktop had a stale proxy (`http://127.0.0.1:10887`) configured in `~/Library/Group Containers/group.com.docker/settings-store.json` that blocked all outbound TLS from containers. Fix: set `ProxyHTTPMode` to `direct` and remove `OverrideProxyHTTP`/`OverrideProxyHTTPS`.

### Embedding Provider (Ollama — NOT DeepSeek)

**DeepSeek does NOT offer an embeddings endpoint.** This is confirmed by:
- `/v1/embeddings` returns 404
- `/v1/models` only lists chat models (`deepseek-v4-flash`, `deepseek-v4-pro`)
- Official docs at `api-docs.deepseek.com` only document `/chat/completions`

**Solution**: Use Ollama with `nomic-embed-text` (768 dimensions) running on the host.

- Ollama must be running on the host: `ollama serve` (or it auto-starts)
- Model must be pulled: `ollama pull nomic-embed-text`
- Accessible from Docker containers via `http://host.docker.internal:11434/v1`
- The OpenAI-compatible API at `/v1/embeddings` returns 768-dim vectors

**mem0 configuration** (in `services/mem0/main.py`):
```python
"embedder": {
    "provider": "openai",
    "config": {
        "api_key": "ollama",              # dummy, ollama doesn't require auth
        "openai_base_url": "http://host.docker.internal:11434/v1",
        "model": "nomic-embed-text",
        "embedding_dims": 768,
    },
},
```

**mem0 LLM configuration** (separate from embeddings):
```python
"llm": {
    "provider": "openai",
    "config": {
        "api_key": "<DEEPSEEK_API_KEY>",
        "openai_base_url": "https://api.deepseek.com/v1",
        "temperature": 0.2,
        "model": "deepseek-chat",
    },
},
```

**Critical mem0 bug workaround**: mem0's `_process_config()` only copies `embedding_dims` from the embedder config to the vector store config when `graph_store` is present in the config. Since we don't use graph_store, we must explicitly set `embedding_model_dims: 768` in the `vector_store.config` section.

**Also**: Do NOT set `OPENAI_API_BASE` as an environment variable in the mem0 container — it overrides the `openai_base_url` in both the LLM and embedder configs, causing the embedder to point at DeepSeek (which has no embeddings endpoint).

---

## mem0 + Qdrant Service

**Image**: `mem0/mem0-api-server:latest`
**Custom entrypoint**: `services/mem0/main.py` (mounted read-only, replaces the default)
**Vector store**: Qdrant (replaces default pgvector)
**Port**: 8888 → 8000

### Key design decisions:
- Qdrant replaces pgvector (no extra Postgres needed, `qdrant-client` already bundled in mem0 image)
- Graph store (Neo4j) disabled by default (`ENABLE_GRAPH=true` to enable)
- History DB stored at `/data/history.db` (persisted via `mem0_history` volume)
- Auth disabled (`AUTH_DISABLED=true`)

### API endpoints:
| Method | Path | Description |
|---|---|---|
| POST | `/memories` | Add memories (`{"messages": [...], "user_id": "..."}`) |
| POST | `/search` | Search memories (`{"query": "...", "user_id": "..."}`) |
| GET | `/memories?user_id=...` | List memories |
| DELETE | `/memories/{id}` | Delete a memory |

---

## SQLite API Service

**Image**: `mem0/mem0-api-server:latest` (reused — already has fastapi/uvicorn)
**Custom app**: `services/sqlite-api/main.py` (mounted read-only)
**Port**: 8090 → 8000

Reuses the mem0 image to avoid pulling `python:3.12-slim` (network was down during initial setup). The image already has `fastapi 0.115.8` + `uvicorn 0.34.0`.

### API endpoints:
| Method | Path | Description |
|---|---|---|
| GET | `/health` | Health check |
| POST | `/answers` | Save answer (`{"question": "...", "answer": "...", "user_id": "..."}`) |
| GET | `/answers?user_id=...` | List answers |

---

## Langfuse v3 Observability

**6-service stack**: web, worker, PostgreSQL, Redis, ClickHouse, MinIO
**Port**: 3000
**Org**: `dify2`, **Project**: `chat-traces`

`chat.py` uses `@observe()` decorators (Langfuse Python SDK v4.6.1) on all functions:
- `chat_request()` — top-level trace
- `retrieve_memories()` — tool
- `ask_agent()` — generation (LLM call)
- `save_memory()` — tool
- `save_answer()` — tool

All 6 sub-operations appear as nested observations under each `chat-request` trace.

---

## Dify Containers (v1.13.3)

10 containers in `dify-docker/`:

| Container | Role |
|---|---|
| `nginx` | Reverse proxy (:80, :443) |
| `api` | Dify console/backend API |
| `worker` | Celery task execution |
| `worker_beat` | Celery beat scheduler |
| `web` | Frontend UI |
| `db_postgres` | PostgreSQL database |
| `redis` | Redis cache/broker |
| `sandbox` | Code execution sandbox |
| `ssrf_proxy` | SSRF protection proxy |
| `plugin_daemon` | Plugin runtime (Python/Node.js) |

### Plugin daemon notes:
- Plugin signature enforcement disabled (required for marketplace install in v1.13.3)
- Settings in `dify-docker/.env`: `FORCE_VERIFYING_SIGNATURE=false`, `ENFORCE_LANGGENIUS_PLUGIN_SIGNATURES=false`
- v1.13.3 has a known regression: local `.difypkg` upload fails at `decode/from_identifier` — use marketplace install instead

### mem0ai Dify Plugin

**Plugin**: `beersoccer/mem0ai:0.3.1`
**Type**: Tool plugin (12 tools)
**Purpose**: Gives the Dify agent autonomous memory management — store, search, update, and delete user memories via mem0 + Qdrant directly (not the mem0 REST API at `:8888`).

**Installed via**: Dify marketplace UI (same signature bypass as DeepSeek plugin).

**Credentials** (configured as `mem0-self-hosted`):
| Credential | Value |
|---|---|
| LLM provider | DeepSeek (`deepseek-chat`, `api.deepseek.com/v1`, temp=0.2) |
| Embedder provider | Ollama (`nomic-embed-text`, `host.docker.internal:11434/v1`, 768 dims) |
| Vector DB | Qdrant (`172.19.0.15:6333`, 768 dims) |

**Tools enabled** (12/12):
`add_memory`, `search_memory`, `update_memory`, `delete_memory`, `list_memories`, `get_memory_history`, `get_all_users`, `delete_all_user_memories`, `reset_memory`, `get_memory`, `get_memory_stats`, `get_memory_by_id`

**Key pitfall — UV mirror**: Plugin daemon containers cannot reach `pypi.org` by default. **Must configure `PIP_MIRROR_URL=https://mirrors.aliyun.com/pypi/simple/` in `dify-docker/.env` BEFORE installing any plugin.** See the big warning at the top of this file.

**Key pitfall — model addition API**: Adding models via `POST .../models` alone returns `{"result":"success"}` but does NOT persist. Must also call `POST .../models/credentials` to save the credential bindings. The UI does both automatically; raw API calls need both steps.

---

### Ollama Model Provider (Dify Plugin)

**Plugin**: `langgenius/ollama:0.1.5`
**Type**: Model provider (`configurate_methods: ["customizable-model"]`)
**Connects to**: `http://host.docker.internal:11434` (host Ollama daemon)

**Registered models**:
| Model | Type | Context Size |
|---|---|---|
| `nomic-embed-text` | text-embedding | 8K |
| `qwen3.5:9b` | llm (chat) | 131K |
| `llama3.1:8b` | llm (chat) | 131K |
| `deepseek-r1:7b` | llm (chat) | 131K |

All models use `base_url: http://host.docker.internal:11434`, authorization name: `ollama-local`.

**Available in**: Agent app model picker → Ollama section. Can be selected alongside DeepSeek models.

**Available local Ollama models** (not all registered in Dify):
`nomic-embed-text`, `tinyllama`, `llama3.1:8b`, `qwen3.5:9b`, `granite4:3b`, `deepseek-coder:1b`, `qwen2.5-coder:7b`, `deepseek-r1:7b`, `qllama/bge-reranker-v2-m3`

---

### SQLite Dify Plugin

**Plugin**: `langgenius/sqlite:0.0.4`
**Type**: Tool plugin (7 tools)
**Purpose**: Gives the Dify agent direct SQLite database access for structured data storage — create tables, insert/query/update/delete rows. Separate from the SQLite API service at `:8090`.

**Installed via**: Dify marketplace UI (same signature bypass as DeepSeek plugin).

**Credentials** (configured as `agent-sqlite`):
| Credential | Value |
|---|---|
| Authorization Name | `agent-sqlite` |
| Database File Path | `/app/storage/data/agent.db` |

**Tools enabled** (7/7):
| Tool | Description |
|---|---|
| `create_table` | Create a new table via SQL CREATE TABLE statement |
| `insert_sql` | Insert rows via SQL INSERT statement |
| `insert_json` | Insert rows via JSON data |
| `select_sql` | Query rows via SQL SELECT statement |
| `update_sql` | Update rows via SQL UPDATE statement |
| `update_json` | Update rows via JSON data |
| `delete_sql` | Delete rows or drop tables via SQL DELETE/DROP |

**Database location**: The DB file lives inside the `plugin_daemon` container at `/app/storage/data/agent.db`. This directory is mounted from the host at `dify-docker/volumes/plugin_daemon/data/` (Docker volume). Data persists across container restarts.

**Key pitfall — DB file must exist**: The SQLite plugin validates that the database file exists before accepting credentials. You must create an empty SQLite file first:
```bash
docker exec dify-docker-plugin_daemon-1 python3 -c \
  "import sqlite3; sqlite3.connect('/app/storage/data/agent.db')"
```
Then fill in the credential form in the plugin UI. Without this step, saving credentials returns a 400 error: `Database file does not exist`.

**E2E verified**: Agent successfully created `test_notes` table, inserted a row, and queried it back via the plugin tools.

---

## Starting Everything

```bash
# 1. Ensure Ollama is running (for embeddings)
ollama serve &   # or it auto-starts as a daemon

# 2. Start all services
cd dify-docker
docker compose --profile postgresql -f docker-compose.yaml -f ../docker-compose.override.yml up -d

# 3. Wait for health checks (~30s)
docker compose --profile postgresql -f docker-compose.yaml -f ../docker-compose.override.yml ps

# 4. Test the CLI
cd ..
uv run chat.py "Hello!"
```

---

## NexusCRM Agent

**App ID**: `390bdd58-bc95-44b0-bbc0-304cb7535459`
**Mode**: agent-chat (function_call strategy)
**Model**: deepseek-chat via `langgenius/deepseek/deepseek`
**Tools**: mem0ai plugin (12 tools) + SQLite plugin (7 tools) = 19 total
**API Key**: stored in `.dify-nexuscrm-credentials`
**DSL**: `agent/nexuscrm-dsl.yaml`
**SQLite DB**: plugin_daemon container `/app/storage/data/agent.db`
**Host path**: `dify-docker/volumes/plugin_daemon/data/`
**SQLite credentials**: Authorization name `agent-sqlite`, configured via Dify Console UI (Plugins → SQLite → API Key Authorization)
**Langfuse**: OTel traces from Dify api/worker/plugin_daemon → Langfuse OTLP endpoint

**Key pitfall — SQLite plugin credentials**: The SQLite plugin must be authorized through the Dify Console UI (Plugins page → SQLite → API Key Authorization Configuration). The DB file must also exist in the plugin_daemon container before saving credentials. Creating tools via raw SQL in `app_model_configs.agent_mode.tools` is NOT sufficient — tools must be added through the Console API (`POST /console/api/apps/{id}/model-config`) and then published via the UI. The app's `model_config` must include all 19 tools (12 mem0ai + 7 sqlite) for the runtime agent to see them.

### Design

- **mem0ai plugin** handles semantic memory (customer personality, sentiment, context, insights)
- **SQLite plugin** handles structured data (accounts, contacts, deals, activities, action_items)
- **Overlapping heuristic**: call outcomes and deal updates written to both systems
- Agent system prompt teaches the dual-storage heuristic with specific rules for when to use each plugin
- Initialized via table creation message (5 tables: accounts, contacts, deals, activities, action_items)

### Spec & Proposal

- Proposal: `proposals.md`
- Design spec: `docs/superpowers/specs/2026-05-24-nexus-crm-proposal-design.md`
- Implementation plan: `docs/superpowers/plans/2026-05-24-nexus-crm-implementation.md`

---

## File Map

```
difyapp3/
├── .env                          # All credentials and ports
├── .dify-credentials             # Dify app API key (DIFY_APP_API_KEY=...)
├── .dify-nexuscrm-credentials   # NexusCRM app ID + API key
├── AGENTS.md                     # This file
├── proposals.md                  # NexusCRM proposal (mem0ai + SQLite dual storage)
├── chat.py                       # Langfuse-traced CLI orchestrator
├── pyproject.toml                # uv project config (langfuse, httpx, python-dotenv)
├── docker-compose.override.yml   # Overlay: mem0, Qdrant, sqlite-api, Langfuse stack
├── agent/
│   ├── nexuscrm-dsl.yaml         # Complete Dify DSL for NexusCRM agent
│   └── nexuscrm-dsl.json         # DSL in JSON format (reference)
├── services/
│   ├── mem0/
│   │   └── main.py               # Custom mem0 entrypoint (Qdrant, DeepSeek LLM, Ollama embeddings)
│   └── sqlite-api/
│       └── main.py               # SQLite answer persistence API
└── dify-docker/                  # Dify v1.13.3 Docker configs
    ├── docker-compose.yaml       # Dify base compose (10 services + plugin_daemon)
    ├── .env                      # Dify-specific env vars (reads by docker compose)
    ├── nginx/                    # Nginx reverse proxy configs
    ├── ssrf_proxy/               # SSRF proxy configs
    └── volumes/                  # Persistent data (plugin_daemon cwd has installed plugins)
```
