# NexusCRM Agent Configuration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Configure the existing Dify agent-chat app (ID `390bdd58-bc95-44b0-bbc0-304cb7535459`) as a NexusCRM account manager with mem0ai plugin (semantic memory) and SQLite plugin (structured database).

**Architecture:** The Dify agent uses ReAct strategy with deepseek-chat model. It has 19 tools enabled (12 mem0ai + 7 SQLite). Implementation consists of: (1) crafting a detailed system prompt that teaches the agent the dual-storage heuristic, (2) configuring it in the Dify UI via browser, (3) initializing SQLite tables, and (4) validating all 4 key scenarios.

**Tech Stack:** Dify v1.13.3 (agent-chat mode), DeepSeek chat model, mem0ai plugin v0.3.1, SQLite plugin v0.0.4, Playwright for browser automation of Dify Console UI.

---

## File Structure

| File | Action | Purpose |
|---|---|---|
| `agent/prompts/system-prompt.md` | Create | The NexusCRM agent system prompt |
| `agent/prompts/init-tables.md` | Create | Table initialization message to seed the agent's SQLite DB |
| `agent/tests/scenario-1.md` | Create | Test script for "Log a Call" scenario |
| `agent/tests/scenario-2.md` | Create | Test script for "Prepare for Meeting" scenario |
| `agent/tests/scenario-3.md` | Create | Test script for "Pipeline Summary" scenario |
| `agent/tests/scenario-4.md` | Create | Test script for "Red Flag Detection" scenario |

---

### Task 1: Create the NexusCRM Agent System Prompt

**Files:**
- Create: `agent/prompts/system-prompt.md`

- [ ] **Step 1: Create the agent prompts directory**

```bash
mkdir -p /Users/bruce/Projects/opencode-go/difyapp3/agent/prompts
```

- [ ] **Step 2: Write the system prompt file**

Create `agent/prompts/system-prompt.md` with the following content:

```markdown
You are NexusCRM, an intelligent account manager for a B2B sales representative. You help the rep manage customer accounts, track deals, log activities, and provide proactive recommendations.

## Dual Storage Model

You have TWO storage systems available. You must understand when to use each:

### mem0ai Tools (Semantic Memory)
Use for: unstructured, recall-oriented data that benefits from semantic search.
- Customer personality traits, communication preferences
- Relationship history, sentiment signals, emotional context
- Conversation summaries, contextual insights
- Anything you'd describe in natural language rather than tables

mem0ai tools: add_memory, search_memory, update_memory, delete_memory, list_memories, get_memory_history, get_all_users, delete_all_user_memories, reset_memory, get_memory, get_memory_stats, get_memory_by_id

### SQLite Tools (Structured Database)
Use for: tabular, queryable data that needs exact filtering and aggregation.
- Accounts (company records)
- Contacts (people at companies)
- Deals (pipeline tracking with amounts and stages)
- Activities (call/meeting/email logs)
- Action items (follow-ups with due dates)

SQLite tools: create_table, insert_sql, insert_json, select_sql, update_sql, update_json, delete_sql

## Database Schema

You have these tables:

**accounts**: id (TEXT PK), name (TEXT), industry (TEXT), website (TEXT), tier (TEXT, default 'standard'), notes (TEXT), created_at (TEXT)

**contacts**: id (TEXT PK), account_id (TEXT), name (TEXT), title (TEXT), email (TEXT), phone (TEXT), notes (TEXT), created_at (TEXT)

**deals**: id (TEXT PK), account_id (TEXT), title (TEXT), amount (REAL), stage (TEXT, default 'discovery'), probability (REAL, default 0.1), close_date (TEXT), created_at (TEXT), updated_at (TEXT)

**activities**: id (TEXT PK), deal_id (TEXT), type (TEXT), summary (TEXT), date (TEXT), created_at (TEXT)

**action_items**: id (TEXT PK), deal_id (TEXT), description (TEXT), due_date (TEXT), status (TEXT, default 'pending'), created_at (TEXT)

If any table does not exist yet, create it using create_table before attempting any other operation.

## Overlap Heuristic Rules

When the rep provides information, decide which storage to use:

| Situation | SQLite? | mem0ai? | Why |
|---|---|---|---|
| Rep mentions a deal amount | YES — insert/update deals | NO | Pure structured data |
| Rep describes customer's tone or personality | NO | YES — add_memory | Pure semantic data |
| Rep logs a call outcome | YES — insert activities | YES — add_memory | Both structured record + semantic context |
| Rep asks about an account | YES — select accounts/deals | YES — search_memory | Both needed for full picture |
| Rep updates deal stage | YES — update deals | YES — add_memory | Record the change AND the context/reason |
| Rep asks for pipeline summary | YES — SQL aggregation | NO | Pure structured query |
| Rep asks about red flags | YES — check deal health | YES — search sentiment | Both structured and semantic signals |
| Rep mentions a new contact | YES — insert contacts | YES if personality/preference info | Structured record; semantic only if rich context |

**General principle**: When in doubt, write to BOTH. Better duplicate information on two paths than lost context. Reading is selective — SQL for exact queries, mem0ai for semantic recall.

## SQL Best Practices

1. Always use UUID-style random strings for IDs (e.g., generate a unique ID)
2. Always ORDER BY date DESC when querying activities
3. Always check if a record exists before inserting (SELECT first, then INSERT if not found)
4. Use ISO 8601 format for all dates (e.g., "2026-05-24T10:30:00Z")
5. For pipeline queries, use GROUP BY stage with COUNT and SUM aggregation
6. When updating deals, always update the updated_at field to current time

## Memory Writing Best Practices

1. Write memories as natural-language sentences, not raw data dumps
2. Always include entity names (person, company) in memories for searchability
3. One insight per memory — don't bundle unrelated facts
4. Extract implicit insights: if the rep says "the CTO pushed back on pricing", store "Acme Corp CTO is price-sensitive — may need discount or value justification"
5. Use the user_id parameter consistently for all memory operations

## Synthesis Behavior

When the rep asks an analytical question:
1. ALWAYS query both storage systems before answering
2. Combine structured data (SQLite) with contextual insights (mem0ai)
3. Present structured data first, then enrich with semantic context
4. Flag any contradictions between what the records show and what the memories suggest

## Conversation Style

- Be concise and professional, like a senior sales ops manager
- Proactively flag overdue action items when relevant
- When the rep mentions a company or person, pull up their context before responding
- If you notice potential issues (stalled deals, overdue follow-ups), mention them unprompted
```

- [ ] **Step 3: Verify the file was created correctly**

```bash
wc -l /Users/bruce/Projects/opencode-go/difyapp3/agent/prompts/system-prompt.md
```

Expected: ~100+ lines

---

### Task 2: Create the Table Initialization Script

**Files:**
- Create: `agent/prompts/init-tables.md`

- [ ] **Step 1: Write the initialization message**

Create `agent/prompts/init-tables.md` with the following content:

```markdown
Please initialize my CRM database by creating all required tables. Create these tables using the SQLite create_table tool:

1. accounts: id (TEXT PRIMARY KEY), name (TEXT NOT NULL), industry (TEXT), website (TEXT), tier (TEXT DEFAULT 'standard'), notes (TEXT), created_at (TEXT NOT NULL)

2. contacts: id (TEXT PRIMARY KEY), account_id (TEXT), name (TEXT NOT NULL), title (TEXT), email (TEXT), phone (TEXT), notes (TEXT), created_at (TEXT NOT NULL)

3. deals: id (TEXT PRIMARY KEY), account_id (TEXT), title (TEXT NOT NULL), amount (REAL), stage (TEXT DEFAULT 'discovery'), probability (REAL DEFAULT 0.1), close_date (TEXT), created_at (TEXT NOT NULL), updated_at (TEXT NOT NULL)

4. activities: id (TEXT PRIMARY KEY), deal_id (TEXT), type (TEXT NOT NULL), summary (TEXT NOT NULL), date (TEXT NOT NULL), created_at (TEXT NOT NULL)

5. action_items: id (TEXT PRIMARY KEY), deal_id (TEXT), description (TEXT NOT NULL), due_date (TEXT), status (TEXT DEFAULT 'pending'), created_at (TEXT NOT NULL)

Create all 5 tables now. Reply with confirmation when done.
```

- [ ] **Step 2: Verify the file**

```bash
cat /Users/bruce/Projects/opencode-go/difyapp3/agent/prompts/init-tables.md
```

---

### Task 3: Configure the Dify Agent via Browser

**Files:**
- Uses: `agent/prompts/system-prompt.md` (from Task 1)

**Prerequisites:**
- All Docker containers running (`docker ps` shows all 20 containers)
- Dify accessible at `http://localhost`
- Browser automation available (Playwright)

This task configures the existing Dify agent-chat app through the Console UI. The Console API requires cookie-based auth that can only be obtained via browser login.

- [ ] **Step 1: Verify all services are running**

```bash
docker ps --format '{{.Names}}' | sort | wc -l
```

Expected: 20 containers

- [ ] **Step 2: Open the Dify Console in a browser**

Navigate to `http://localhost` and log in with admin credentials from `.env` (`DIFY_ADMIN_EMAIL` / `DIFY_ADMIN_PASSWORD`).

- [ ] **Step 3: Navigate to the agent app**

Go to the app with ID `390bdd58-bc95-44b0-bbc0-304cb7535459`. From the Dify dashboard, find the agent-chat app and click into it.

- [ ] **Step 4: Open the agent configuration**

Click on "Orchestrate" or "Agent Configuration" to access the system prompt and tool settings.

- [ ] **Step 5: Update the system prompt**

Replace the current agent instructions with the full content from `agent/prompts/system-prompt.md`. Paste the entire prompt into the system prompt field.

- [ ] **Step 6: Verify tool configuration**

Confirm that all 19 tools are enabled:
- mem0ai plugin: 12 tools (add_memory, search_memory, update_memory, delete_memory, list_memories, get_memory_history, get_all_users, delete_all_user_memories, reset_memory, get_memory, get_memory_stats, get_memory_by_id)
- SQLite plugin: 7 tools (create_table, insert_sql, insert_json, select_sql, update_sql, update_json, delete_sql)

If any tools are missing, enable them in the tool configuration panel.

- [ ] **Step 7: Verify model configuration**

Confirm the model is set to `deepseek-chat` via the DeepSeek plugin.

- [ ] **Step 8: Save and publish**

Save the configuration and publish the app.

---

### Task 4: Initialize SQLite Tables

**Files:**
- Uses: `agent/prompts/init-tables.md` (from Task 2)

This task sends the table initialization message to the agent to create the CRM schema in SQLite.

- [ ] **Step 1: Open the agent chat interface**

In the Dify Console, open the preview/debug chat for the agent app.

- [ ] **Step 2: Send the initialization message**

Paste the content from `agent/prompts/init-tables.md` as a chat message to the agent.

- [ ] **Step 3: Verify table creation**

The agent should execute 5 `create_table` calls. Confirm all return success. If any fail, check that the SQLite plugin credentials are configured (database file path: `/app/storage/data/agent.db`).

- [ ] **Step 4: Verify tables exist**

Ask the agent: "Show me all tables in the database." The agent should use `select_sql` to list: accounts, contacts, deals, activities, action_items.

---

### Task 5: Create Test Scenario Scripts

**Files:**
- Create: `agent/tests/scenario-1.md`
- Create: `agent/tests/scenario-2.md`
- Create: `agent/tests/scenario-3.md`
- Create: `agent/tests/scenario-4.md`

- [ ] **Step 1: Create tests directory**

```bash
mkdir -p /Users/bruce/Projects/opencode-go/difyapp3/agent/tests
```

- [ ] **Step 2: Write Scenario 1 — Log a Call**

Create `agent/tests/scenario-1.md`:

```markdown
## Scenario 1: Log a Call

**Input message:**
"Just got off a call with Sarah Chen at Acme Corp. She's the new VP Engineering. Deal is now at $180K, moving to evaluation stage. She seemed excited but mentioned their CTO wants to see a security audit before signing. Follow up by next Friday with the audit report."

**Expected agent actions (verify each occurred):**
1. search_memory("Sarah Chen Acme Corp") — checks for prior context
2. select_sql on contacts — checks if Sarah Chen exists
3. insert_sql on contacts — creates Sarah Chen (VP Engineering, Acme Corp)
4. update_sql or insert_sql on deals — records $180K amount, "evaluation" stage
5. insert_sql on activities — logs the call
6. insert_sql on action_items — creates follow-up for security audit by next Friday
7. add_memory — stores semantic context about Sarah, the deal, and the CTO concern

**Success criteria:**
- [ ] All 7+ tool calls executed without errors
- [ ] Contact record exists in SQLite for Sarah Chen
- [ ] Deal amount updated to $180K with stage "evaluation"
- [ ] Activity logged with call summary
- [ ] Action item created with due date next Friday
- [ ] At least 1 memory added with contextual info about Sarah/CTO
- [ ] Agent confirms the logging with a summary response
```

- [ ] **Step 3: Write Scenario 2 — Prepare for Meeting**

Create `agent/tests/scenario-2.md`:

```markdown
## Scenario 2: Prepare for a Meeting

**Prerequisite:** Scenario 1 must have been run first (so Acme Corp data exists).

**Input message:**
"I have a QBR with Acme Corp tomorrow. What should I know?"

**Expected agent actions (verify each occurred):**
1. select_sql on accounts — retrieves Acme Corp account details
2. select_sql on deals — retrieves active deals for Acme
3. select_sql on activities (ORDER BY date DESC, LIMIT 10) — recent interactions
4. select_sql on action_items (status = 'pending') — open follow-ups
5. search_memory("Acme Corp") — retrieves semantic context (Sarah, CTO, preferences)

**Success criteria:**
- [ ] Agent queried BOTH SQLite and mem0ai before answering
- [ ] Response includes account details (company info)
- [ ] Response includes deal status ($180K, evaluation stage)
- [ ] Response mentions the pending security audit follow-up
- [ ] Response includes semantic context (Sarah's excitement, CTO's security concern)
- [ ] Response is structured as a meeting briefing, not raw data
```

- [ ] **Step 4: Write Scenario 3 — Pipeline Summary**

Create `agent/tests/scenario-3.md`:

```markdown
## Scenario 3: Pipeline Summary

**Prerequisite:** At least Scenario 1 completed (one deal in pipeline).

**Input message:**
"Give me a pipeline summary for this quarter."

**Expected agent actions (verify each occurred):**
1. select_sql with GROUP BY stage — pipeline breakdown by stage
2. select_sql for deals at risk — active deals not yet in final stages
3. select_sql for overdue action items
4. search_memory for deal risks/concerns — optional, checks for known blockers

**Success criteria:**
- [ ] Agent used SQL aggregation (GROUP BY, COUNT, SUM), NOT semantic search, for pipeline data
- [ ] Response includes total pipeline value
- [ ] Response breaks down deals by stage
- [ ] Response identifies the Acme deal in evaluation stage
- [ ] Response mentions any overdue follow-ups
- [ ] Response provides actionable recommendations
```

- [ ] **Step 5: Write Scenario 4 — Red Flag Detection**

Create `agent/tests/scenario-4.md`:

```markdown
## Scenario 4: Red Flag Detection

**Prerequisite:** Scenarios 1-3 completed (data in both systems).

**Input message:**
"Anything concerning across my accounts?"

**Expected agent actions (verify each occurred):**
1. search_memory with negative sentiment keywords — retrieves concerns, frustrations
2. select_sql for low-probability active deals
3. select_sql for overdue action items
4. Cross-references both data sources

**Success criteria:**
- [ ] Agent searched mem0ai for sentiment signals (frustrated, at risk, competitor, etc.)
- [ ] Agent queried SQLite for deal health metrics
- [ ] Response mentions the Acme security audit follow-up as an action item
- [ ] Response cross-references the CTO's security concern (from memory) with the pending action item (from SQLite)
- [ ] Response is proactive — agent flags issues without being asked about specific accounts
```

---

### Task 6: Execute and Validate All Scenarios

**Files:**
- Uses: `agent/tests/scenario-1.md` through `scenario-4.md`

- [ ] **Step 1: Execute Scenario 1 (Log a Call)**

Send the input message from `scenario-1.md` to the agent in the Dify debug chat. Observe tool calls and verify against expected actions.

- [ ] **Step 2: Verify Scenario 1 results**

Check each success criterion from `scenario-1.md`. If any fail, note the failure reason.

- [ ] **Step 3: Execute Scenario 2 (Prepare for Meeting)**

Send the input message from `scenario-2.md`. Verify the agent queries both SQLite and mem0ai.

- [ ] **Step 4: Verify Scenario 2 results**

Check each success criterion from `scenario-2.md`.

- [ ] **Step 5: Execute Scenario 3 (Pipeline Summary)**

Send the input message from `scenario-3.md`. Verify the agent uses SQL aggregation, not semantic search.

- [ ] **Step 6: Verify Scenario 3 results**

Check each success criterion from `scenario-3.md`.

- [ ] **Step 7: Execute Scenario 4 (Red Flag Detection)**

Send the input message from `scenario-4.md`. Verify cross-referencing between both storage layers.

- [ ] **Step 8: Verify Scenario 4 results**

Check each success criterion from `scenario-4.md`.

- [ ] **Step 9: Document results**

Create a summary of which scenarios passed/failed and any agent behavior that needs adjustment in the system prompt.

---

### Task 7: Finalize and Update AGENTS.md

**Files:**
- Modify: `AGENTS.md`

- [ ] **Step 1: Add NexusCRM section to AGENTS.md**

Add a section documenting the NexusCRM agent configuration:

```markdown
## NexusCRM Agent

**App ID**: `390bdd58-bc95-44b0-bbc0-304cb7535459`
**Mode**: agent-chat (ReAct)
**Model**: deepseek-chat
**Tools**: mem0ai (12) + SQLite (7) = 19
**System prompt**: `agent/prompts/system-prompt.md`
**SQLite tables**: accounts, contacts, deals, activities, action_items
**DB location**: plugin_daemon container `/app/storage/data/agent.db`
**Host path**: `dify-docker/volumes/plugin_daemon/data/`

### Key design decisions
- mem0ai plugin handles semantic memory (personality, sentiment, context)
- SQLite plugin handles structured data (accounts, deals, activities)
- Overlapping heuristic: call outcomes and deal updates written to both
- Agent initialized via `agent/prompts/init-tables.md` message
```

- [ ] **Step 2: Verify AGENTS.md updated correctly**

```bash
grep -c "NexusCRM" /Users/bruce/Projects/opencode-go/difyapp3/AGENTS.md
```

Expected: 2+ matches
