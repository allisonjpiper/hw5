# Campus Customs Harness

The complete reference for the Campus Customs agent desk: the database, the MCP server, the five agents, the API, the dashboard, and the safety rules that hold it together.

**Source of truth:** `data/campus_customs_new.db` (the working copy of the original `data/campus_customs.db`, which is never modified and is the seed for resets). Every read and write goes through the MCP server in `mcp_server/server.py`.

**Contents**
1. [Database tables](#1-database-tables)
2. [MCP tools](#2-mcp-tools)
3. [The five agents](#3-the-five-agents)
4. [Audit trail](#4-audit-trail)
5. [API routes](#5-api-routes)
6. [Dashboard](#6-dashboard)
7. [Safety rules](#7-safety-rules)
8. [How a ticket gets resolved](#8-how-a-ticket-gets-resolved)
9. [Running everything](#9-running-everything)

---

## 1. Database tables

There are 12 tables. The **9 shop tables** come from the original database and describe one shop on one day: what's on the shelves, what it costs, who the shop owes, how much cash it has, and the tickets to work. The **3 agent tables** are created by the MCP server so the agents' work (and humans' decisions) is stored in the database too.

### 1.1 `desk` — today's date (1 row)

| Column | Meaning | Why it matters to the agents |
|---|---|---|
| `date_today` | The shop's "current date" (`2026-08-31`) | Agents must use this date instead of the real clock when deciding what is overdue or due soon. For example, invoice 501 is already overdue and rent is due in 2 days. |
| `notes` | Free-text notes for the day (currently empty) | Lets the agent leave or read daily context for the shop. |

### 1.2 `inventory` — what's on the shelves (10 rows)

Primary key is `(sku, size)`, so each product has one row per size.

| Column | Meaning | Why it matters to the agents |
|---|---|---|
| `sku` | Product code (e.g. `CC-HOOD-NAVY`) | Links stock to `pricing` and `tickets`. Agents look products up by this code. |
| `name` | Customer-facing product name | Used when the agent replies to a customer. |
| `size` | S / M / L / XL, or `OS` (one size) | Stock is tracked per size, so an agent must check the exact size requested. |
| `qty` | Units on hand | The agent checks this before promising an order. Several sizes are at **0** (Bulldog Tee S, Crest Mug), and hoodie M has only **8**. |
| `location` | Aisle where the item lives | Tells staff where to pick the item when fulfilling an order. |

### 1.3 `pricing` — cost and price per product (4 rows)

| Column | Meaning | Why it matters to the agents |
|---|---|---|
| `sku` | Product code (one price per SKU, all sizes) | Joins to `inventory` and `tickets`. |
| `unit_cost` | What the shop pays per unit | Sets the floor for any discount. An agent should never sell below cost. |
| `list_price` | Normal retail price | The default quote. The difference from `unit_cost` is the margin an agent can give up in a discount. For example, a hoodie is $58 − $22 = $36 margin. |

### 1.4 `vendors` — suppliers (3 rows)

| Column | Meaning | Why it matters to the agents |
|---|---|---|
| `id` | Vendor ID | Referenced by `invoices.vendor_id`. |
| `name` | Vendor name | Shown when the agent tells the owner who is being paid or reordered from. |
| `specialty` | What the vendor supplies (apparel reprint, small goods, courier) | Tells the agent which vendor to use to restock which product. |
| `lead_days` | Days to deliver | Lets the agent tell a customer realistically when an out-of-stock item will arrive. |

### 1.5 `leases` — the shop's rent (1 row)

| Column | Meaning | Why it matters to the agents |
|---|---|---|
| `id` | Lease ID | Referenced by `tickets.lease_id` (ticket 102). |
| `space_name` / `landlord` | Which space and who is owed | Identifies who the rent payment goes to. |
| `monthly_rent` | $2,400 | One of the largest cash outflows. The agent has to keep enough cash for it. |
| `next_due` | `2026-09-02` | Compared against `desk.date_today` to know how urgent the rent is. |
| `notes` | Free-text notes | Context, such as late-fee terms, if filled in. |

### 1.6 `cash_accounts` — money available (1 row)

| Column | Meaning | Why it matters to the agents |
|---|---|---|
| `name` | Account name (`checking`) | Must match `payments.account` when a payment is recorded. |
| `balance` | $3,400 | The hard limit on what can be paid. Rent ($2,400) plus invoice 501 ($840) totals $3,240, which leaves only $160, so agents must check the balance before paying anything. |
| `date` | Date the balance was recorded | Shows whether the balance is current. |

### 1.7 `payments` — payment log (0 rows at the start)

Starts empty. Every payment is written here by the pay tool (`pay_approved_request`), and only after a human approves it.

| Column | Meaning | Why it matters to the agents |
|---|---|---|
| `id` | Payment ID | Unique record per payment. |
| `kind` | What was paid (e.g. rent, invoice) | Tells you which table `ref_id` points to. |
| `ref_id` | ID of the lease or invoice that was paid | Ties the payment to what it settled, which prevents double-paying. |
| `amount` | Amount paid | Must be subtracted from `cash_accounts.balance`. |
| `account` | Which cash account paid it | Links to `cash_accounts.name`. |
| `paid_at` | Timestamp | Part of the audit trail. |
| `approved_by` | Who approved the payment | The human-approval / audit field. Agents should not move money without a recorded approver. |

### 1.8 `invoices` — bills from vendors (1 row)

| Column | Meaning | Why it matters to the agents |
|---|---|---|
| `id` | Invoice ID (501) | Referenced by `tickets.invoice_id` and `payments.ref_id`. |
| `vendor_id` | Which vendor sent the bill | Joins to `vendors` (Bulldog Print Co). |
| `amount` | $840 | Cash needed to pay it. |
| `due_date` | `2026-08-28` | Already **overdue** as of `date_today`. |
| `status` | `open` / paid | The agent updates this to paid after paying, and checks it so an invoice isn't paid twice. |
| `description` | "Rush reprint CC-TEE-WHITE S" | Explains that this bill restocks the out-of-stock Bulldog Tee S, which connects it to ticket 101. |

### 1.9 `tickets` — the work queue (3 rows)

Each ticket is a request the agents need to handle. Tickets use the foreign keys to connect to every other table.

| Column | Meaning | Why it matters to the agents |
|---|---|---|
| `id` | Ticket ID | Lets each ticket be tracked and closed. |
| `type` | `customer_order`, `rent_notice`, `price_override` | Decides which agent or tool should handle the ticket. |
| `requester` | Who asked | Who the agent responds to. |
| `subject` / `notes` | What they want, in plain text | The actual request the agent has to understand. |
| `sku`, `size`, `qty` | Product details (order tickets) | Checked against `inventory` and `pricing`. |
| `lease_id` | Linked lease (rent tickets) | Points to the rent owed. |
| `invoice_id` | Linked invoice | Ticket 101 points to invoice 501, the reprint that would restock the requested tee. |
| `status` | `open` / closed | The agent closes a ticket once it's handled. |
| `created_at` | When the ticket arrived | Ordering and urgency. |

**Tickets at the start (seed data):**
- **101 – customer_order:** Tauhid Zaman wants 1 Bulldog Tee, size S. Stock is **0**, and the restock depends on unpaid, overdue invoice 501.
- **102 – rent_notice:** $2,400 rent due 2026-09-02, against a $3,400 checking balance.
- **103 – price_override:** Yale AI Club wants 20 hoodies in size M at a bulk discount, but only **8** are in stock. Any discount has to stay above the $22 unit cost.

### How the tables connect

```
tickets ──sku/size──▶ inventory ──sku──▶ pricing
   │
   ├──lease_id────▶ leases
   └──invoice_id──▶ invoices ──vendor_id──▶ vendors

payments ──ref_id──▶ leases / invoices
payments ──account─▶ cash_accounts
desk.date_today = the "now" used for every due-date check
```

### 1.10 Agent tables (created by the MCP server)

`CREATE TABLE IF NOT EXISTS` runs on every MCP connection, so these come back right after a reset. The 9 shop tables keep their original schema.

| Table | Columns that matter | Written by | Why it matters |
|---|---|---|---|
| `approval_requests` | kind (`invoice` / `rent` / `purchase_order`), ref_id, vendor_id, payee, amount, account, memo, ticket_id, requested_by (agent), status (`pending` → `approved` / `rejected` → `paid`), approved_by (**human only**), decided_at, payment_id | `request_payment_approval` creates; `human_decide_approval` approves or rejects (human); `pay_approved_request` marks paid | The queue that keeps money from moving without a person. Every payment traces back to one row here and a named approver. |
| `message_drafts` | ticket_id, audience (`customer` / `vendor` / `landlord`), recipient, subject, body, author_agent, created_at, status (`draft_not_sent` or `superseded`) | `save_message_draft` | Every outgoing message stays a draft for a human to send. A newer draft to the same person on the same ticket marks the older one `superseded`, so a stale version (e.g. an outdated price) can't be sent by mistake. |
| `ticket_decisions` | ticket_id, status, decision, decided_by, decided_at | `record_ticket_decision` (Boss), `human_resolve_ticket` (human) | The history of every decision on a ticket. Follow-up runs read it, and the dashboard shows the latest one. |

---

## 2. MCP tools

`mcp_server/server.py` (FastMCP, stdio) is the **only** path to the database, for the agents and for the FastAPI backend alike. Nothing in `backend/` opens the database. Each tool does one specific job, returns only values read from the database, and enforces its own safety checks in code. Each tool is named for the job it does. (Before the final submission the tools had placeholder names `tool_1`…`tool_15` in the same order, so older audit-trail entries and the Problem 6 predictions use those.) Claude Code connects to the server through `.mcp.json`; the backend connects through `backend/config.py`.

| Tool | Purpose | Reads | Writes | Who may call it |
|---|---|---|---|---|
| `check_order_fulfillment` | **Ticket 101 fact sheet** (customer order): requested sku/size/qty, stock on hand, list price, `can_fill_now`, linked restock invoice with days overdue, vendor and lead days | tickets, inventory, pricing, invoices, vendors, desk | — | boss, inventory, customer_service |
| `check_rent_coverage` | **Ticket 102 fact sheet** (rent notice): lease, landlord, rent, next due, days until due, rent already paid, cash, open invoices, cash after rent and after rent + invoices | tickets, leases, cash_accounts, invoices, vendors, payments, desk | — | boss, accounting, facilities |
| `price_bulk_order` | **Ticket 103 fact sheet** (bulk order / price override): fillable now, shortfall, stock by size, unit cost, list price, margin, max discount %, price floor, full-order totals, vendors | tickets, inventory, pricing, vendors | — | boss, inventory, accounting, customer_service |
| `list_ticket_queue` | **Ticket queue**: desk date and every unresolved ticket (or all, with `include_resolved`) with its decision history | tickets, ticket_decisions, desk | — | boss, customer_service, backend |
| `lookup_inventory_pricing` | **Inventory & pricing** for one sku or the whole catalogue, with an out-of-stock list | inventory, pricing | — | inventory, accounting, customer_service |
| `list_vendors_invoices` | **Vendors & invoices**: specialty, lead days, invoices with days overdue, payments made against them | vendors, invoices, payments, desk | — | inventory, accounting |
| `get_cash_position` | **Cash position**: balances, open invoices, rent due within `rent_window_days` (default 30), payments log, approval queue, cash free after all obligations, plus `warnings` for later rent that free cash can't cover; states there are no cash inflows | cash_accounts, invoices, leases, payments, approval_requests, desk | — | accounting, facilities, backend |
| `request_payment_approval` | **Request approval** for an invoice, rent, or PO payment. **No money moves.** Refuses wrong amounts, closed invoices, duplicates, and anything over cash minus what's already queued | cash_accounts, invoices, vendors, leases, approval_requests | approval_requests | accounting |
| `pay_approved_request` | **Pay tool**: executes one **human-approved** request in one transaction. Refuses if not approved, approver is an agent, already paid, balance ≤ 0, or it would overdraw | approval_requests, cash_accounts, invoices, leases, desk | payments, cash_accounts, invoices **or** leases, approval_requests | accounting, backend (`dashboard`) |
| `save_message_draft` | **Save a draft** (customer / vendor / landlord). Never sends. Recipient must already be in the database. Identical drafts are deduplicated and older ones superseded | tickets, vendors, leases, message_drafts | message_drafts | inventory, facilities, customer_service |
| `list_approval_queue` | **Approval queue & drafts** (with full draft bodies) | approval_requests, message_drafts | — | all agents, backend |
| `record_ticket_decision` | **Record the Boss's decision** and set ticket status (`in_progress` / `awaiting_approval` / `resolved`). Boss only; can't resolve while money is pending | tickets, approval_requests | tickets, ticket_decisions | boss |
| `human_decide_approval` | **Human only: approve or reject** a pending request with the person's name | approval_requests | approval_requests | backend only |
| `human_reset_database` | **Human only: reset** the database (`confirm="RESET"`): backs up to `data/backups/`, restores the 9 shop tables from `data/campus_customs.db`, empties the agent tables | seed DB, all tables | all tables | backend only |
| `human_resolve_ticket` | **Human only: mark a ticket resolved** with the person's name and a note. Refused while a payment is pending or approved | tickets, approval_requests | tickets, ticket_decisions | backend only |

No tool can increase a cash balance. `human_decide_approval`–`human_resolve_ticket` appear in no agent's allowlist.

---

## 3. The five agents

Built with **Pydantic AI** in `backend/`. Every agent uses **`gpt-6-luna`** through Portkey (`PORTKEY_API_KEY` from `.env`) via OpenAI's Responses API (gpt-6-luna rejects function tools with reasoning on Chat Completions) and has its **own model instance**, **own prompt** (`backend/prompts/<agent>.md`), **own MCP tool allowlist** (the shared MCP connection is filtered per agent), **own usage limits**, and **own agent loop** (`ShopAgent.run_loop` in `backend/base.py`). The loop walks the Pydantic AI graph node by node, checks the token budget before each model call, and appends every step to the audit trail. Agents send work to each other with a `delegate` tool, and delegation is **fully connected**: every agent can delegate to every other agent. On each run, the ticket's routing plan narrows who is actually reachable.

| Agent | Job | MCP tools | Can delegate to | Limits (requests / tool calls) | Returns |
|---|---|---|---|---|---|
| **Boss** (`boss.py`) | Reads each ticket, decides who works on it, hands work out **one agent at a time**, checks the numbers, and makes and records the **final decision** | check_order_fulfillment, check_rent_coverage, price_bulk_order, list_ticket_queue, list_approval_queue, record_ticket_decision | inventory, accounting, facilities, customer_service | 12 / 12 | `BossDecision` |
| **Inventory** (`inventory.py`) | Stock by sku/size, shortfalls, restock plans with vendors (specialty, lead days, reprint cost), vendor drafts | check_order_fulfillment, price_bulk_order, lookup_inventory_pricing, list_vendors_invoices, save_message_draft, list_approval_queue | all four other agents (incl. Boss) | 10 / 10 | `SpecialistReport` |
| **Accounting** (`accounting.py`) | Cash, invoices, margins, discount floors, quotes only for what can be filled; the **only** agent that queues payments/POs for approval or runs the pay tool | check_rent_coverage, price_bulk_order, lookup_inventory_pricing, list_vendors_invoices, get_cash_position, request_payment_approval, pay_approved_request, list_approval_queue | all four other agents (incl. Boss) | 12 / 12 | `SpecialistReport` |
| **Facilities** (`facilities.py`) | The shop space: lease, landlord, rent, due dates, rent coverage, landlord drafts | check_rent_coverage, get_cash_position, save_message_draft, list_approval_queue | all four other agents (incl. Boss) | 8 / 8 | `SpecialistReport` |
| **Customer Service** (`customer_service.py`) | Writes customer messages as drafts (never sent). Offers in-stock alternatives and leaves out internal details (vendors, invoices, cash) | check_order_fulfillment, price_bulk_order, list_ticket_queue, lookup_inventory_pricing, save_message_draft, list_approval_queue | all four other agents (incl. Boss) | 8 / 8 | `SpecialistReport` |

**Data types** (`backend/models.py`): `SpecialistReport` (summary, facts with source tool, actions, approval ids, drafts, recommendations, needs_human, blockers), `BossDecision` (assigned agents, decision, status, reasons, approval ids, draft ids, human actions, risks), `Fact`, `DraftRef`, `DeskDeps` (run id, ticket, budget, team, depth, chain, allowed agents), `AuditEntry`, plus the API request/response bodies.

**Supporting files:** `base.py` (shared loop + delegation), `team.py` (builds the team), `config.py` (model + MCP connection), `audit.py` (append-only audit writer), `budget.py` (token guard), `desk.py` (one desk run), `cli.py` (command line), `main.py` (FastAPI).

### Routing plan: minimum agents per ticket

`TICKET_PLANS` in `backend/boss.py`. The Boss reads the ticket's fact sheet itself, then delegates only for what it can't do: queuing money (Accounting) and writing to the customer (Customer Service). The plan is **enforced** in the `delegate` tool. Any hand-off outside it, including nested ones, is refused and logged as `delegation_refused`.

| Ticket type | Boss reads | Agents, in order | Why the others aren't needed |
|---|---|---|---|
| `customer_order` (101) | `check_order_fulfillment` | accounting → customer_service | `check_order_fulfillment` already has stock, restock invoice, vendor and lead days |
| `rent_notice` (102) | `check_rent_coverage` | accounting | `check_rent_coverage` already has lease, rent, due date and cash coverage |
| `price_override` (103) | `price_bulk_order` | accounting → customer_service | `price_bulk_order` already has shortfall, stock by size, cost/floor and vendors |

Inventory and Facilities stay available for ticket types without a plan, and for questions the fact sheets can't answer.

### Delegation guardrails
- **One hand-off at a time:** the Boss runs with `parallel_tool_calls=False`, so Customer Service always receives Accounting's exact numbers. (Problem 9 found that parallel hand-offs produced two drafts with different prices.)
- **Depth limit of 2** (Boss → specialist → specialist), and no delegating to an agent already in the chain (so a specialist can't hand work back to the Boss that called it), so loops can't form.
- **Follow-up runs:** when a ticket already has decisions, the Boss checks `list_approval_queue` first. If its payments are paid and its draft exists, it records `resolved` without re-delegating (a few tenths of a cent).

---

## 4. Audit trail

`output/audit_trail.json` is a single JSON array that is only ever **appended to**. `backend/audit.py` reads it, adds the entry, and writes it back atomically; it refuses to overwrite a file that isn't an array. Resets don't clear it. Each entry has `timestamp`, `run_id`, `loop_id`, `agent`, `event`, `ticket_id`, `depth`, `chain`, `step`, and `detail`. The API key is scrubbed from every entry.

| Events | Logged when |
|---|---|
| `desk_start`, `ticket_queue_read`, `desk_end` | A desk run starts, reads the queue (`list_ticket_queue`), and ends (decisions + token spend) |
| `loop_start`, `loop_end`, `loop_error` | An agent loop begins (task, model, prompt, tools, limits), returns its structured output, or fails |
| `model_request`, `model_response` | Before each model call (input, projected spend) and after (tool calls with arguments, text, tokens, cost) |
| `delegation_sent`, `delegation_returned`, `delegation_refused` | Work handed between agents and the report that came back, or why it was refused |
| `budget_approval_required` | The next call would pass the approved token budget |
| `human_approval`, `human_rejection`, `payment_executed`, `payment_refused`, `human_resolution`, `db_reset` | Human actions through the API |

---

## 5. API routes

FastAPI app in `backend/main.py`. Start it from the `backend` folder with `../.venv/bin/uvicorn main:app --reload --port 8000`. Base URL **http://localhost:8000**, interactive docs at **http://localhost:8000/docs**. At startup it opens one MCP connection and builds the agent team once. Only one agent run happens at a time; approvals, resolves and resets return `409` while a run is in progress. CORS allows the dashboard at **http://localhost:5180** (and any other localhost port).

| Method & URL | What it does | MCP tools | Body / params |
|---|---|---|---|
| `GET http://localhost:8000/` | Service info, route list, whether a run is in progress | — | — |
| `GET http://localhost:8000/tickets` | All tickets: type, requester, subject, notes, sku/size/qty, status, **`open_or_closed`** (`closed` = resolved), pending approval ids, active draft ids, latest decision | list_ticket_queue, list_approval_queue | — |
| `GET http://localhost:8000/tickets/{id}` | One ticket (`404` if unknown) | list_ticket_queue, list_approval_queue | — |
| `POST http://localhost:8000/tickets/{id}/run` | **Run the agent team on one ticket**; returns `run_id`, the `BossDecision`, and token spend (20–60 s) | all agent tools | optional `{"approve_budget": 0.50, "approved_by": "Name"}`; over $0.50 with no name → `403`, budget hit → `402`, busy → `409` |
| `POST http://localhost:8000/tickets/{id}/resolve` | **A named human marks the ticket resolved** (refused while a payment is pending or approved, or if the name is an agent's) | human_resolve_ticket | `{"closed_by": "Name", "note": "…"}` |
| `GET http://localhost:8000/activity` | **What the agents did recently**: per run, each agent's model calls, **MCP tools used (with counts)**, summary, delegations, cost, errors, full decisions; plus the last 20 human actions | — (reads audit trail) | `?runs=5`, `?ticket_id=101` |
| `GET http://localhost:8000/activity/events` | **Live step-by-step feed** (one readable line per audit step) for polling during a run | — (reads audit trail) | `?after=<index>`, `?limit=200` |
| `GET http://localhost:8000/approvals` | Approval queue and message drafts | list_approval_queue | `?status=pending\|approved\|rejected\|paid` |
| `POST http://localhost:8000/approvals/{id}/approve` | **A human approves, then the cash moves**: `human_decide_approval` records the approver, `pay_approved_request` pays and updates every table. Returns the payment, new checking balance, and open approvals left on the ticket (`paid:false` + reason if the pay tool refuses) | human_decide_approval, pay_approved_request, get_cash_position, list_approval_queue | `{"approver": "Name", "reason": "…"}` |
| `POST http://localhost:8000/approvals/{id}/reject` | A human rejects a request; no money moves | human_decide_approval | `{"approver": "Name", "reason": "…"}` |
| `GET http://localhost:8000/cash/checking` | **Checking balance**, as-of date, open obligations, free after obligations | get_cash_position | — |
| `GET http://localhost:8000/cash` | Full cash position | get_cash_position | — |
| `POST http://localhost:8000/reset` | **Reset the database for a fresh run** (backup first; audit trail kept) | human_reset_database | `{"confirm": "RESET"}` |

---

## 6. Dashboard

React + Vite + TypeScript in `frontend/`. Start it with `npm run dev` and open **http://localhost:5180**. Port 5180 is used because 5173–5175 are taken by other class projects. The API base comes from `VITE_API_BASE` (default `http://localhost:8000`). Deep links like `#/tickets/101`, `#/approvals`, and `#/cash` open a ticket or tab directly. The design reasoning is in `output/design.md`.

| Area | What an employee can do | Routes used |
|---|---|---|
| **Top bar** | See the checking balance and cash free after bills, connection and run status. Enter your name once (used for approvals). Reset the database (type `RESET` to confirm). | `/cash/checking`, `/reset` |
| **Tickets** | Open/closed list with status, approvals and drafts. Ticket detail with the request, a 4-step tracker (agents → approve payments → send drafts → resolve), **Run agent team** with a **live feed**, an **agent summary** (Boss decision, who did what with which tools and cost, reasons, to-dos, risks, earlier runs since the last reset), inline approve/reject, drafts with Copy, and **Mark resolved** (disabled with a reason until nothing is pending) | `/tickets`, `/tickets/{id}/run`, `/tickets/{id}/resolve`, `/activity`, `/activity/events`, `/approvals`, `/approvals/{id}/approve`, `/approvals/{id}/reject` |
| **Approvals** | Pending requests with totals and checking-if-all-approved. The approve dialog shows checking before → after and blocks overdrafts; reject takes a reason. Paid/rejected history | `/approvals`, `/approvals/{id}/*` |
| **Cash** | Checking balance, a bar of rent / invoices / POs / free cash, a line-by-line breakdown, and the payments log with approvers | `/cash` |
| **Agent activity** | Recent runs with each agent's calls and tools, token spend, human-action log, latest steps | `/activity`, `/activity/events` |

---

## 7. Safety rules

### Required rules
1. **Human approval for any money changing hands.** Agents can only *request* a payment (`request_payment_approval` → `pending`). A person approves through `human_decide_approval` with their name. `pay_approved_request` refuses anything not approved, or approved under an agent's name. Prices and quotes count as money decisions too: the Boss only recommends them, and a human approves them by resolving the ticket.
2. **Payments update the tables.** `pay_approved_request` writes `payments`, lowers `cash_accounts`, marks the invoice `paid` or advances the lease's `next_due`, and marks the approval `paid`, all in one transaction (everything or nothing).
3. **No unlogged work.** Every agent loop, model call, tool call, tool result, delegation, and human action is appended to `output/audit_trail.json` by the code itself, not left to the model. Database writes also leave rows in `approval_requests`, `message_drafts`, `ticket_decisions`, and `payments`.
4. **No debt.** `pay_approved_request` refuses if the balance is ≤ 0 or the payment would go below zero. `request_payment_approval` won't queue more than the balance minus what's already queued. The dashboard's approve button is disabled for overdrafts.
5. **No cash comes in, only out.** No tool can raise a balance. Amounts must be positive, sales are never recorded as income, and `get_cash_position` treats the current balance as the ceiling on all spending.
6. **No real contact.** No agent has a send, email, or call tool. `save_message_draft` only saves drafts addressed to people already in the database, and every draft stays logged for a human to review and send.
7. **Human approval before spending more than $0.50 on tokens.** Each run has a $0.50 budget (priced for `gpt-6-luna` via `genai_prices`). Before each model call, `backend/budget.py` projects the spend and stops with `budget_approval_required` if it would pass the limit. A higher budget needs a named approver (`--approved-by` or `approved_by` in the API).

### Additional rules
8. **Facts only from MCP.** Agents have no database, file, or web access. Every number in a report cites its source tool, and if a report and a tool disagree, the tool wins.
9. **The shop's date is `desk.date_today`**, never the real clock.
10. **Never sell below cost, and quote only what can be delivered.** The floor is `pricing.unit_cost`. Quotes cover only the quantity fillable now unless a reprint is funded.
11. **No double payments.** `request_payment_approval` rejects a duplicate pending request, and `pay_approved_request` refuses a closed invoice or an already-paid request.
12. **Least privilege.** Each agent sees only its own MCP tools. Only Accounting can queue payments or pay, and only the Boss records agent decisions. `human_decide_approval`, `human_reset_database`, and `human_resolve_ticket` are human-only (backend), and agent names are rejected as approvers or closers.
13. **No closing with money pending.** `record_ticket_decision` and `human_resolve_ticket` refuse to resolve a ticket while it has a pending or approved request.
14. **Bounded loops.** Per-agent request and tool-call limits, delegation depth ≤ 2, no delegating back up the chain, minimum-agent routing enforced per ticket, and the Boss hands off one agent at a time.
15. **No stale messages.** A newer draft supersedes older unsent drafts to the same recipient on the same ticket, and the dashboard hides superseded drafts.
16. **No promises the data can't support.** No stock that isn't on hand, no delivery date earlier than lead days plus approval, and no internal details (vendors, invoices, cash, agent names) in customer messages.
17. **Resets are recoverable.** `human_reset_database` backs up the database before restoring the original `data/campus_customs.db`, requires the word `RESET`, and leaves the audit trail intact.
18. **Secrets stay out of logs.** `PORTKEY_API_KEY` is redacted from the audit trail.

---

## 8. How a ticket gets resolved

1. **Reset** (optional): `POST /reset` → original data from `data/campus_customs.db`, all tickets `open`, checking $3,400.
2. **Agents work it:** `POST /tickets/{id}/run` → the Boss reads the fact sheet and routes per plan; Accounting queues any payment (`pending`); Customer Service saves the draft; the Boss records `awaiting_approval`.
3. **A human approves:** `POST /approvals/{id}/approve` → the cash moves and every affected table updates. Or reject.
4. **Close it:** either `POST /tickets/{id}/run` again (the Boss sees everything paid and records `resolved`), or a human calls `POST /tickets/{id}/resolve` (needed when the remaining decision is a price, as on 103).
5. **Staff send the drafts** themselves.

**Problem 9 result** (details in `output/resolved_tickets.json`, `output/desk_tickets.html`, `output/resolved_board.html`):

| Ticket | Agents | Human approval | Cash | Closed by |
|---|---|---|---|---|
| 101 · Bulldog Tee S | Accounting → Customer Service | #1 invoice 501, $840 (Allison Piper) | −$840 | Boss, follow-up run |
| 102 · Rent | Accounting | #2 rent, $2,400 (Allison Piper) | −$2,400 | Boss, follow-up run (flagged the October shortfall) |
| 103 · Bulk hoodies | Accounting → Customer Service | Quote 8 × $52 = $416, size-mix alternative (Allison Piper) | $0 | Human, `/resolve` |

All runs used **gpt-6-luna**. Checking went from $3,400 to **$160** (verified in `cash_accounts`), with $0.0204 in tokens. Open risk, which the agents flagged themselves through the `get_cash_position` warning: October rent ($2,400, due 2026-10-02) can't be covered from $160 with no inflows, a $2,240 shortfall.

---

## 9. Running everything

```bash
# backend (FastAPI + MCP + agents), from Homework 5/backend
../.venv/bin/uvicorn main:app --reload --port 8000

# dashboard, from Homework 5/frontend
npm run dev          # http://localhost:5180

# command-line desk run (optional), from Homework 5
.venv/bin/python -m backend.cli --ticket 101

# MCP server alone (normally started by the backend or Claude Code via .mcp.json)
.venv/bin/python mcp_server/server.py
```

When stopping the backend, stop the whole process tree (uvicorn reloader, worker, and its MCP child process), not only whatever holds port 8000.
