# Campus Customs — Multi-Agent Desk (MGT 409, Homework 5)

A five-agent team (Boss, Inventory, Accounting, Facilities, Customer Service) built with **Pydantic AI** on **gpt-6-luna** via Portkey. The team works the Campus Customs shop's open tickets through an **MCP server** over a SQLite database, a **FastAPI** backend exposes the desk to a **React + Vite + TypeScript** dashboard, and every payment waits for a human.

- **Full reference** (tables, MCP tools, agents, routes, dashboard, safety rules): [`output/harness.md`](output/harness.md)
- **Results:** [`output/desk_tickets.html`](output/desk_tickets.html) (Expected / Actual / Cash / Reflection), [`output/resolved_tickets.json`](output/resolved_tickets.json), [`output/resolved_board.html`](output/resolved_board.html)

## Repository layout

```
AI_prompts.md          prompts I gave the vibe coder, by problem
requirements.txt       Python dependencies
.env.example           copy to .env and add PORTKEY_API_KEY (the real .env is never committed)
.mcp.json              Claude Code project MCP config (campus-customs server)
data/
  campus_customs.db       original database (never modified; the seed for resets)
  campus_customs_new.db   working copy the agents use (currently in the resolved end state)
mcp_server/
  server.py               FastMCP server: the only path to the database (15 tools)
  README.md
backend/
  main.py                 FastAPI app (routes for the dashboard)
  models.py               data types (agent outputs, deps, audit entries, API bodies)
  boss.py inventory.py accounting.py facilities.py customer_service.py   the five agents
  base.py team.py desk.py config.py audit.py budget.py cli.py           agent loop, wiring, guards
  prompts/                boss.md inventory.md accounting.md facilities.md customer_service.md
frontend/                 React + Vite + TypeScript dashboard
output/                   harness.md, mcp_smoke.json, desk_tickets.html, design.md,
                          resolved_tickets.json, resolved_board.html (+ board_screenshots/),
                          audit_trail.json, github_url.txt
```

## Setup

Requires Python 3.12+ (developed on 3.14) and Node 20+.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env        # then put your PORTKEY_API_KEY in .env
cd frontend && npm install && cd ..
```

## Start the MCP server

You normally don't start it by hand. The backend launches it over stdio at startup (`backend/config.py`), and Claude Code launches it from `.mcp.json` when you open this folder. To run it directly:

```bash
.venv/bin/python mcp_server/server.py
```

It reads and writes `data/campus_customs_new.db` (override with `CAMPUS_CUSTOMS_DB`), and creates the agent tables (`approval_requests`, `message_drafts`, `ticket_decisions`) if they're missing.

## Start the FastAPI backend

```bash
cd backend
../.venv/bin/uvicorn main:app --reload --port 8000
```

The API is at http://localhost:8000, with interactive docs at http://localhost:8000/docs. It opens one MCP connection and builds the agent team at startup.

## Start the dashboard

```bash
cd frontend
npm run dev
```

Open http://localhost:5180. The dashboard calls the backend at `http://localhost:8000` (set `VITE_API_BASE` in `frontend/.env.local` to change it), and the backend's CORS settings allow this origin.

## Reset the database

The working database ships in its resolved end state. To start fresh, use one of these:

- **Dashboard:** click **Reset data** in the top bar and type `RESET`.
- **API:**
  ```bash
  curl -X POST http://localhost:8000/reset -H "Content-Type: application/json" -d '{"confirm":"RESET"}'
  ```

Either one backs up the current database to `data/backups/`, restores the 9 shop tables from `data/campus_customs.db`, and empties the agent tables. All tickets go back to `open`, and checking returns to $3,400. The audit trail is kept.

## Full three-ticket workflow

From a fresh reset, either in the dashboard or with the API calls shown:

1. **Run the agents on each ticket.** The Boss reads the ticket's fact sheet and routes the work using the minimum agents (`TICKET_PLANS` in `backend/boss.py`):
   ```bash
   curl -X POST http://localhost:8000/tickets/101/run   # customer order → Accounting, Customer Service
   curl -X POST http://localhost:8000/tickets/102/run   # rent notice    → Accounting
   curl -X POST http://localhost:8000/tickets/103/run   # bulk discount  → Accounting, Customer Service
   ```
   Accounting queues payments as **pending** approval requests (#1 invoice 501 for $840, #2 rent for $2,400). Customer Service saves unsent drafts. Each ticket ends up `awaiting_approval`.
2. **A human approves the payments.** Approving makes the payment: it records the row in `payments`, lowers checking, and marks the invoice paid or advances the lease.
   ```bash
   curl -X POST http://localhost:8000/approvals/1/approve -H "Content-Type: application/json" -d '{"approver":"Your Name"}'
   curl -X POST http://localhost:8000/approvals/2/approve -H "Content-Type: application/json" -d '{"approver":"Your Name"}'
   ```
3. **Close the tickets.**
   - **101 and 102:** run them again. The Boss sees the payments were made and records `resolved`.
   - **103:** a price is an owner decision, so a human resolves it after approving the quote:
     ```bash
     curl -X POST http://localhost:8000/tickets/103/resolve -H "Content-Type: application/json" -d '{"closed_by":"Your Name","note":"Approved quote"}'
     ```
4. **Check the result.** `GET /tickets` shows all three `closed`. `GET /cash/checking` shows **$160** ($3,400 − $840 − $2,400). `GET /activity` shows which agents worked and which MCP tools they used. Staff send the drafts themselves.

Every step is appended to `output/audit_trail.json`.

## Safety rules (summary)

- Human approval before any money moves.
- Payments update every affected table in one transaction.
- No unlogged work.
- No debt.
- No incoming cash.
- No real emails or calls; drafts only.
- Human approval for more than $0.50 of tokens per run.
- Facts only come from MCP.

The full list of 18 rules is in [`output/harness.md`](output/harness.md#7-safety-rules).

## Command-line run (optional)

```bash
.venv/bin/python -m backend.cli --ticket 101
```
