# Wave 4 Work Orders + Campaign Chat History Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep existing campaign tasks while adding campaign-level Work Orders that support chat-driven content generation and per-work-order conversation history queries.

**Architecture:** Introduce a new Work Order domain model linked to campaign and optional task, with dedicated message history. Reuse existing chatbot command + trace/audit security patterns so all mutations remain governed and traceable. Extend Campaign UI with a Work Orders panel and Work Order chat/history view.

**Tech Stack:** Next.js 16 App Router, TypeScript, FastAPI, Postgres persistence layer, existing chatbot intent framework.

---

## Chunk 1: Backend domain + persistence

### Task 1: Add Work Order schemas and persistence methods

**Files:**
- Modify: `services/campaign_service/app/main.py`
- Modify: `services/campaign_service/app/persistence.py`

- [ ] Step 1: Add Pydantic schemas for work order and work order message request/response models.
- [ ] Step 2: Add Postgres table initialization for `work_orders` and `work_order_messages` with indexes on `(campaign_id, created_at)` and `(work_order_id, created_at)`.
- [ ] Step 3: Add persistence CRUD/list methods for work orders and messages.
- [ ] Step 4: Add in-memory fallback structures matching existing trace/task style.
- [ ] Step 5: Run `python -m compileall app` and fix typing/runtime issues.

### Task 2: Add Work Order API endpoints

**Files:**
- Modify: `services/campaign_service/app/main.py`

- [ ] Step 1: Add `GET/POST /api/v1/campaigns/{campaign_id}/work-orders`.
- [ ] Step 2: Add `GET/PATCH /api/v1/work-orders/{work_order_id}`.
- [ ] Step 3: Add `GET/POST /api/v1/work-orders/{work_order_id}/messages`.
- [ ] Step 4: Enforce existing internal key and actor boundary patterns for write paths.
- [ ] Step 5: Emit trace/audit events for work order create/update/message append actions.

## Chunk 2: Chatbot command integration

### Task 3: Extend chatbot intents/commands for Work Orders

**Files:**
- Modify: `lib/types/chatbot.ts`
- Modify: `lib/chatbot/intents.ts`
- Modify: `lib/chatbot/commands.ts`
- Modify: `app/api/chat/execute/route.ts`

- [ ] Step 1: Add intents: `create_work_order`, `list_work_orders`, `update_work_order`, `generate_work_order_content`, `show_work_order_history`.
- [ ] Step 2: Add slot parsing for campaign id / work order id / content request.
- [ ] Step 3: Implement command handlers calling new backend endpoints.
- [ ] Step 4: Keep high-risk actions governed by existing confirmation + actor rules.
- [ ] Step 5: Ensure denied and accepted requests remain audit logged.

## Chunk 3: Frontend UX (Campaign page)

### Task 4: Add Work Orders panel and per-work-order chat history

**Files:**
- Modify: `app/campaigns/page.tsx`
- Modify: `lib/api/campaigns.ts`
- Modify: `lib/i18n/translations.ts`

- [ ] Step 1: Add API client types/functions for work order list/detail/message endpoints.
- [ ] Step 2: Add UI section under campaigns for work order list and filters.
- [ ] Step 3: Add selected work order detail panel with editable status/assignee/description.
- [ ] Step 4: Add work order message timeline + input for chat-driven content generation.
- [ ] Step 5: Add i18n keys (EN/ZH/JA) for all new labels and states.

## Chunk 4: Verification + hardening

### Task 5: End-to-end verification

**Files:**
- Modify: `scripts/chatbot-phase-d-smoke.mjs`
- Modify: `scripts/wave3-release-gate.mjs` (or add Wave4 gate command)
- Modify: `package.json`

- [ ] Step 1: Extend smoke script with work order create/update/history query flow.
- [ ] Step 2: Add negative checks for unauthorized work order mutation.
- [ ] Step 3: Run `npm run check:i18n`.
- [ ] Step 4: Run `npm run lint`.
- [ ] Step 5: Run `npm run build`.
- [ ] Step 6: Run `python -m compileall app`.
- [ ] Step 7: Run updated smoke script and verify PASS.
- [ ] Step 8: Run Oracle final read-only audit on Wave 4 deltas.
