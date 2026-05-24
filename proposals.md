# Proposal A: NexusCRM — AI Account Manager for B2B Sales

**Domain**: B2B Sales & Customer Success

## What It Does

An intelligent account manager Dify agent that maintains deep customer context across interactions. A single sales rep converses with it to manage accounts, log activities, analyze deal health, and get proactive recommendations.

## Dual Storage via Dify Plugins

The agent uses two Dify tool plugins for persistent storage:

- **mem0ai plugin** (12 tools: `add_memory`, `search_memory`, `update_memory`, `delete_memory`, `list_memories`, `get_memory_history`, `get_all_users`, `delete_all_user_memories`, `reset_memory`, `get_memory`, `get_memory_stats`, `get_memory_by_id`) — semantic memory layer backed by Qdrant vector store. Stores unstructured, recall-oriented data: customer personality traits, relationship history, sentiment signals, conversation summaries, preferences. Retrieved via semantic search, not exact keys.

- **SQLite plugin** (7 tools: `create_table`, `insert_sql`, `insert_json`, `select_sql`, `update_sql`, `update_json`, `delete_sql`) — structured database layer. Stores tabular, queryable data: accounts, contacts, deals, activities, pipeline stages. Retrieved via SQL queries with exact predicates. Database file at `/app/storage/data/agent.db` inside the plugin_daemon container.

### Overlapping Heuristic

Both systems can hold data about the same entity. After a call the agent writes the deal amount and stage to SQLite (structured record), and simultaneously extracts the customer's tone, urgency, and key concerns into mem0ai (semantic recall). The agent uses mem0ai for "what do I remember about this customer" and SQLite for "what's the current pipeline state."

**Why it's production-grade**: Real CRM systems need exactly this pattern — hot semantic context for conversational recall, cold structured storage for pipeline analytics and reporting. The overlap zone (loading account data into memory, writing structured records from conversation) is the core value proposition.

---

## Data Model

### SQLite Schema (Structured Layer)

The agent uses `create_table` and `insert_sql` to initialize these tables on first use:

```sql
CREATE TABLE IF NOT EXISTS accounts (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    industry TEXT,
    website TEXT,
    tier TEXT DEFAULT 'standard',
    notes TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS contacts (
    id TEXT PRIMARY KEY,
    account_id TEXT,
    name TEXT NOT NULL,
    title TEXT,
    email TEXT,
    phone TEXT,
    notes TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS deals (
    id TEXT PRIMARY KEY,
    account_id TEXT,
    title TEXT NOT NULL,
    amount REAL,
    stage TEXT DEFAULT 'discovery',
    probability REAL DEFAULT 0.1,
    close_date TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS activities (
    id TEXT PRIMARY KEY,
    deal_id TEXT,
    type TEXT NOT NULL,
    summary TEXT NOT NULL,
    date TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS action_items (
    id TEXT PRIMARY KEY,
    deal_id TEXT,
    description TEXT NOT NULL,
    due_date TEXT,
    status TEXT DEFAULT 'pending',
    created_at TEXT NOT NULL
);
```

### mem0ai Memory (Semantic Layer)

No schema — the agent stores free-form memories scoped by `user_id` (the sales rep's identifier):

| Memory Category | Example | Retrieval |
|---|---|---|
| Customer personality | "VP Engineering at Acme — prefers technical deep-dives, dislikes sales-speak" | Semantic search by topic |
| Relationship history | "Had a tense call in March about pricing; recovered with a custom demo" | Semantic recall by context |
| Sentiment signals | "Seemed frustrated with onboarding timeline; mentioned evaluating competitor" | Semantic search |
| Preferences | "Always wants meeting agendas 24h ahead; prefers Slack over email" | Semantic search |
| Conversation summaries | "QBR covered 3 topics: renewal concerns, new feature requests, expansion budget" | Semantic recall |

---

## Overlap Heuristic Rules

| Action | SQLite? | mem0ai? | Rationale |
|---|---|---|---|
| Rep mentions a deal amount | `insert_sql` / `update_sql` on `deals` | No | Pure structured data |
| Rep describes customer's tone | No | `add_memory` | Pure semantic data |
| Rep logs a call outcome | `insert_sql` on `activities` | `add_memory` | Structured record + semantic context |
| Rep asks "what do I know about Acme?" | `select_sql` on `accounts`/`deals` | `search_memory` | Both needed for full picture |
| Rep updates deal stage | `update_sql` on `deals` | `add_memory` | Record the change, remember the context |
| Rep asks for pipeline summary | `select_sql` with aggregation | No | Pure structured query |
| Rep asks "any red flags?" | `select_sql` on deal health | `search_memory` for sentiment | Both structured and semantic signals |
| Rep mentions a new contact | `insert_sql` on `contacts` | `add_memory` if context-rich | Structured record; semantic only if there's personality/preference info |

**General principle**: When in doubt, write to both. It's better to have duplicate information retrievable via two paths than to lose context. Reading is always selective — SQL for exact queries, mem0ai for semantic recall.

---

## Key Scenarios

### Scenario 1: Log a Call

> Rep: "Just got off a call with Sarah Chen at Acme Corp. She's the new VP Eng. Deal is now at $180K, moving to evaluation stage. She seemed excited but mentioned their CTO wants to see a security audit before signing. Follow up by next Friday with the audit report."

Agent actions:

1. `search_memory("Sarah Chen Acme Corp")` — recall prior context
2. `select_sql("SELECT * FROM contacts WHERE name LIKE '%Sarah%Chen%'")` — check if Sarah exists
3. `insert_sql` on `contacts` — create Sarah Chen (VP Eng, Acme Corp) if new
4. `update_sql` on `deals` — update amount to $180K, stage to "evaluation"
5. `insert_sql` on `activities` — log the call with summary
6. `insert_sql` on `action_items` — create follow-up: send security audit by next Friday
7. `add_memory("Sarah Chen at Acme Corp is the new VP Engineering. Excited about the product but CTO requires security audit before signing. $180K deal in evaluation stage.")` — semantic memory
8. `add_memory("Acme Corp CTO is security-conscious — needs audit report before any deal closes.")` — extracted insight

### Scenario 2: Prepare for a Meeting

> Rep: "I have a QBR with Acme tomorrow. What should I know?"

Agent actions:

1. `select_sql` on `accounts` — account details
2. `select_sql` on `deals` — current pipeline
3. `select_sql` on `activities` (recent 10, ORDER BY date DESC) — recent interactions
4. `select_sql` on `action_items` (status = 'pending') — open items
5. `search_memory("Acme Corp preferences concerns sentiment")` — semantic context
6. Synthesizes briefing: account status, deal health, open items, contextual notes

### Scenario 3: Pipeline Summary

> Rep: "Give me a pipeline summary for this quarter."

Agent actions:

1. `select_sql` — pipeline by stage with amounts: `SELECT stage, COUNT(*), SUM(amount) FROM deals GROUP BY stage`
2. `select_sql` — deals at risk: nearing close date but not in final stages
3. `select_sql` — overdue action items
4. `search_memory("deal risks concerns blockers")` — semantic signals about stalled deals
5. Synthesizes summary with deal health assessment and recommendations

### Scenario 4: Red Flag Detection

> Rep: "Anything concerning across my accounts?"

Agent actions:

1. `search_memory("frustrated unhappy at risk competitor evaluating leaving")` — negative signals
2. `select_sql` — low-probability active deals
3. `select_sql` — overdue follow-ups
4. Cross-references structured and semantic data, e.g.: "Acme's CTO wanted a security audit — that follow-up is overdue. Beta Inc. was noted as 'evaluating competitors' — that deal has been in negotiation for 6 weeks."

---

## Agent Configuration

| Setting | Value |
|---|---|
| Dify App Mode | `agent-chat` (ReAct strategy) |
| Model | `deepseek-chat` |
| Enabled Tools | mem0ai plugin (12/12 tools) + SQLite plugin (7/7 tools) = 19 tools total |
| Streaming | Required (agent-chat apps only support streaming mode) |
| mem0ai user_id | The sales rep's identifier (e.g., `rep-<name>`) — passed to all mem0ai tool calls to scope memories to this rep |

### Initial Setup

On first conversation (or when no tables exist), the agent should use `create_table` to initialize all 5 tables. This can also be done manually via the agent before the first real interaction. The agent's instructions should include the full CREATE TABLE statements so it can recreate them if needed.

### Agent Prompt Strategy

The agent's system instructions should cover:

1. **Dual storage model** — explain when to use mem0ai vs SQLite vs both
2. **SQLite table schemas** — so the agent knows column names and types for generating correct SQL
3. **Heuristic rules** — the overlap rules from the table above
4. **SQL patterns** — always ORDER BY date DESC for activities, always check before insert for contacts/accounts, use UUIDs for IDs
5. **Memory writing style** — write memories as natural-language sentences, not raw data dumps; include entity names for searchability
6. **Synthesis behavior** — when asked for analysis, always pull from both systems before answering

---

## Success Criteria

The NexusCRM agent is successful when:

- A sales rep can converse naturally and have the agent correctly route data to both storage layers
- Asking "what do I know about X?" pulls from both mem0ai and SQLite and synthesizes a coherent answer
- Pipeline queries use SQL aggregation exclusively, never semantic search
- Sentiment/concern queries use mem0ai search, supplemented by structured data
- After logging a call, the agent writes to both systems with appropriate data splits (structured facts to SQLite, semantic context to mem0ai)
- The agent proactively surfaces overdue items, red flags, and meeting preparation notes
- The agent does not lose context between sessions — mem0ai persists across conversations, and SQLite retains all structured records
