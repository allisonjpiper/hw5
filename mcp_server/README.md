# Campus Customs MCP Server

## Why we need it

The agents (`backend/`, Pydantic AI) can't open the SQLite database directly. They can only act through tools. This MCP server (built with FastMCP) is the **only** path between the agents and the shop's data:

- Every shop fact an agent uses (stock, prices, balances, dates, names) comes from one of these tools, so the agents don't guess.
- Every database write (approval requests, payments, drafts, ticket decisions) also goes through a tool, and **the safety rules are enforced here in code**, not left to the model. Examples: no payment without a human approver, no overdrawing, no paying twice, no sending messages.
- The agents get no arbitrary SQL. Each tool does one specific job and returns the same structured answer every time.

Any agent that speaks MCP (Claude Code via `.mcp.json`, or the Pydantic AI team via `backend/config.py`) plugs into the same server, so the tools only have to be written once.

## Database file

`../data/campus_customs_new.db`, the working copy of `campus_customs.db`. The path is set by `DB_PATH` in `server.py` and can be overridden with the `CAMPUS_CUSTOMS_DB` environment variable (used for testing on a scratch copy). The shop's "today" comes from `desk.date_today` (2026-08-31), not the real clock.

On startup the server adds three agent tables if they don't exist yet: `approval_requests`, `message_drafts`, and `ticket_decisions`. The original 9 tables keep their schema.

## Tools

Each tool is named for the job it does. The three ticket fact sheets are `check_order_fulfillment` (101), `check_rent_coverage` (102), and `price_bulk_order` (103). (Early drafts used placeholder names `tool_1`…`tool_15`; older audit-trail entries still show them.)

### Read-only

| Tool | Purpose | What it returns | Tables read |
|---|---|---|---|
| `check_order_fulfillment` | **Ticket 101** (`customer_order`): can this order be filled? | Requested sku/size/qty, stock on hand, location, list price, `can_fill_now`, the linked restock invoice (amount, due date, status, days overdue, vendor, lead days) | tickets, inventory, pricing, invoices, vendors, desk |
| `check_rent_coverage` | **Ticket 102** (`rent_notice`): can the shop afford rent? | Lease (space, landlord, rent, next due), days until due, rent already paid, cash balances, open invoices, cash after rent and after rent + all open invoices | tickets, leases, cash_accounts, invoices, vendors, payments, desk |
| `price_bulk_order` | **Ticket 103** (`price_override`): how much of a bulk order, and at what floor? | Qty requested/on hand/fillable/shortfall, stock by size, unit cost, list price, margin, max discount % before a loss, price floor, full-order totals, vendor list | tickets, inventory, pricing, vendors |
| `list_ticket_queue` | Ticket queue | Desk date and every unresolved ticket (all columns) with its decision history. `include_resolved=true` shows all tickets | tickets, ticket_decisions, desk |
| `lookup_inventory_pricing` | Inventory + pricing | Every size of a sku (or the whole catalogue): qty, location, unit cost, list price, margin, plus an out-of-stock list | inventory, pricing |
| `list_vendors_invoices` | Vendors + invoices | Each vendor (specialty, lead days) with its invoices, days overdue, and payments made against them | vendors, invoices, payments, desk |
| `get_cash_position` | Cash position | Balances, open invoices, upcoming rent, payments log, approval queue, `cash_free_after_all_obligations`, plus a note that there are no cash inflows | cash_accounts, invoices, leases, payments, approval_requests, desk |
| `list_approval_queue` | Approval queue + drafts | All approval requests (optionally filtered by status) and saved message drafts (with full body) | approval_requests, message_drafts |

### Writes

| Tool | Purpose | Writes | Refuses when |
|---|---|---|---|
| `request_payment_approval` | **Request human approval** for an invoice, rent, or purchase-order payment. **No money moves.** | `approval_requests` (status `pending`) | amount ≤ 0; invoice missing/not open/amount mismatch; rent ≠ `monthly_rent`; unknown vendor; duplicate pending request; amount > balance minus already-queued requests; unknown agent |
| `pay_approved_request` | **Pay tool**: execute one human-approved payment | `payments` (new row), `cash_accounts` (balance − amount), `invoices.status='paid'` **or** `leases.next_due` + 1 month, `approval_requests.status='paid'`, all in one transaction | request not `approved`; `approved_by` empty or an agent name; already paid; balance ≤ 0 (**no remaining cash**); payment would go negative (**no debt**); invoice no longer open |
| `save_message_draft` | **Save a draft** message to a customer, vendor, or landlord. **Never sends.** | `message_drafts` (status `draft_not_sent`) | recipient isn't a ticket requester / vendor / landlord in the database; bad audience. An identical draft returns the existing id instead of saving a duplicate, and a newer draft to the same recipient on the same ticket marks older unsent ones `superseded` |
| `record_ticket_decision` | **Record the Boss's final decision** and set the ticket status | `tickets.status`, `ticket_decisions` | caller isn't `boss`; invalid status; trying to mark `resolved` while a payment for the ticket is still pending or approved |

### Human-only (FastAPI backend)

These tools are in **no** agent's allowlist. Only the dashboard backend (`backend/main.py`) calls them, on behalf of a named person.

| Tool | Purpose | Writes | Refuses when |
|---|---|---|---|
| `human_decide_approval` | **Approve or reject** a pending payment / PO request (`decision="approve"` or `"reject"`, `approver` = a human's name). Approving doesn't move money; the backend then calls `pay_approved_request`. | `approval_requests` (status, approved_by, decided_at) | approver empty or an agent/`dashboard` name; request not `pending`; bad decision |
| `human_resolve_ticket` | **Mark a ticket resolved** (`closed_by` = a human's name, optional `note`) after the agents' run | `tickets.status`, `ticket_decisions` | name empty or an agent name; ticket missing or already resolved; ticket still has a pending/approved payment |
| `human_reset_database` | **Reset the database** for a fresh run (`confirm="RESET"`). Backs up the current DB to `data/backups/pre_reset_<timestamp>.db`, restores the 9 shop tables from `data/campus_customs.db`, and empties the agent tables, all in one transaction. | all tables | confirm isn't exactly `RESET`; seed file missing |

`pay_approved_request` also accepts `requested_by="dashboard"` when the payment was approved by a human through the backend.

`get_cash_position` counts rent as an obligation only when it is due within `rent_window_days` (default 30), so next month's rent doesn't count against cash right after this month's is paid. Its `warnings` list still flags any later rent that free cash can't cover.

No tool can increase a cash balance: the shop has no incoming cash.

### Which agent may use which tool

The tool allowlists are set in each agent file in `backend/` and enforced by filtering the shared MCP connection per agent.

| Agent | Tools |
|---|---|
| Boss | check_order_fulfillment, check_rent_coverage, price_bulk_order, list_ticket_queue, list_approval_queue, record_ticket_decision |
| Inventory | check_order_fulfillment, price_bulk_order, lookup_inventory_pricing, list_vendors_invoices, save_message_draft, list_approval_queue |
| Accounting | check_rent_coverage, price_bulk_order, lookup_inventory_pricing, list_vendors_invoices, get_cash_position, request_payment_approval, pay_approved_request, list_approval_queue |
| Facilities | check_rent_coverage, get_cash_position, save_message_draft, list_approval_queue |
| Customer Service | check_order_fulfillment, price_bulk_order, list_ticket_queue, lookup_inventory_pricing, save_message_draft, list_approval_queue |

## Running it

From the `Homework 5` folder:

```bash
.venv/bin/python mcp_server/server.py
```

This runs over stdio, the default transport for MCP clients. You normally don't start it by hand: Claude Code starts it from `.mcp.json`, and the backend starts it from `backend/config.py` when you run the API:

```bash
cd backend
../.venv/bin/uvicorn main:app --reload --port 8000
```

or a command-line desk run:

```bash
.venv/bin/python -m backend.cli
```
