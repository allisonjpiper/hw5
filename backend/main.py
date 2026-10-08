"""
main.py

FastAPI backend for the Campus Customs desk dashboard (Problem 7).

Start it from the backend folder:

    cd backend
    ../.venv/bin/uvicorn main:app --reload --port 8000

Every shop fact and every database change goes through the campus-customs
MCP server (one stdio connection opened at startup). The only file this app
reads directly is output/audit_trail.json, for the activity report, and
every human action taken here (approve, reject, pay, reset) is appended to
that same trail.

Routes (interactive docs at http://localhost:8000/docs):
    GET  /                         service info and route list
    GET  /tickets                  all tickets, open or closed
    GET  /tickets/{id}             one ticket
    POST /tickets/{id}/run         run the agent team on one ticket
    POST /tickets/{id}/resolve     a human marks a ticket resolved
    GET  /activity                 recent agent runs and the tools they used
    GET  /activity/events          live step-by-step feed (poll while agents run)
    GET  /approvals                payment / PO approval queue
    POST /approvals/{id}/approve   human approves, then the payment is made
    POST /approvals/{id}/reject    human rejects a request
    GET  /cash/checking            checking balance
    GET  /cash                     full cash position
    POST /reset                    reset the database for a fresh run
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections import Counter, defaultdict
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

# Allow `uvicorn main:app` from inside backend/ as well as `backend.main:app` from the project root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, HTTPException, Query  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from pydantic_ai.exceptions import ModelRetry  # noqa: E402

from backend import audit  # noqa: E402
from backend.budget import BudgetApprovalRequired, TokenBudget  # noqa: E402
from backend.config import build_mcp_toolset  # noqa: E402
from backend.desk import new_run_id, run_desk  # noqa: E402
from backend.models import (  # noqa: E402
    ActivityResponse,
    AgentActivity,
    ApprovalDecisionRequest,
    ApproveAndPayResponse,
    CheckingBalance,
    LiveEvent,
    LiveEventsResponse,
    ResetRequest,
    ResolveTicketRequest,
    RunActivity,
    RunTicketRequest,
    RunTicketResponse,
    TicketsResponse,
    TicketSummary,
)
from backend.team import build_team  # noqa: E402

state: dict[str, Any] = {}
desk_lock = asyncio.Lock()  # one agent run at a time; approvals and resets wait for it


@asynccontextmanager
async def lifespan(app: FastAPI):
    mcp = build_mcp_toolset()
    async with mcp:
        state["mcp"] = mcp
        state["team"] = build_team(mcp)
        yield
    state.clear()


app = FastAPI(
    title="Campus Customs Desk API",
    description="Tickets, agent runs, activity, human payment approvals, cash, and reset, all over the campus-customs MCP server.",
    version="1.0.0",
    lifespan=lifespan,
)
# The Vite dashboard (frontend/, `npm run dev`) runs on http://localhost:5180. Any other
# localhost port is allowed too, so a preview build or a second dev server also works.
DASHBOARD_ORIGINS = ["http://localhost:5180", "http://127.0.0.1:5180"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=DASHBOARD_ORIGINS,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_methods=["*"],
    allow_headers=["*"],
)


async def call(tool: str, args: dict | None = None) -> Any:
    """Call an MCP tool; turn its validation errors into HTTP 400s."""
    try:
        return await state["mcp"].direct_call_tool(tool, args or {})
    except ModelRetry as exc:
        raise HTTPException(status_code=400, detail=str(exc.message if hasattr(exc, "message") else exc))


def ensure_idle() -> None:
    if desk_lock.locked():
        raise HTTPException(status_code=409, detail="An agent run is in progress. Try again when it finishes.")


# ---------------------------------------------------------------------------
# Info
# ---------------------------------------------------------------------------


@app.get("/")
async def root() -> dict:
    return {
        "service": "Campus Customs Desk API",
        "docs": "/docs",
        "agent_run_in_progress": desk_lock.locked(),
        "routes": [
            {"method": r.methods and sorted(r.methods - {"HEAD"})[0], "path": r.path, "name": r.name}
            for r in app.routes
            if getattr(r, "include_in_schema", False)
        ],
    }


# ---------------------------------------------------------------------------
# 1. Tickets: open or closed
# ---------------------------------------------------------------------------


async def ticket_summaries() -> TicketsResponse:
    queue = await call("list_ticket_queue", {"include_resolved": True})
    approvals = await call("list_approval_queue")
    pending = defaultdict(list)
    for a in approvals["approval_requests"]:
        if a["status"] in ("pending", "approved"):
            pending[a["ticket_id"]].append(a["id"])
    drafts = defaultdict(list)
    for d in approvals["message_drafts"]:
        if d["status"] != "superseded":
            drafts[d["ticket_id"]].append(d["id"])

    tickets = []
    for t in queue["tickets"]:
        last = t["decision_history"][-1] if t["decision_history"] else {}
        tickets.append(TicketSummary(
            id=t["id"], type=t["type"], requester=t["requester"], subject=t["subject"], status=t["status"],
            notes=t.get("notes"), sku=t.get("sku"), size=t.get("size"), qty=t.get("qty"), created_at=t.get("created_at"),
            open_or_closed="closed" if t["status"] == "resolved" else "open",
            pending_approval_ids=pending[t["id"]], draft_ids=drafts[t["id"]],
            last_decision=last.get("decision"), last_decided_at=last.get("decided_at"),
        ))
    return TicketsResponse(today=queue["today"], tickets=tickets)


@app.get("/tickets", response_model=TicketsResponse)
async def list_tickets() -> TicketsResponse:
    """Every ticket with its status and whether it is open or closed (closed = resolved)."""
    return await ticket_summaries()


@app.get("/tickets/{ticket_id}", response_model=TicketSummary)
async def get_ticket(ticket_id: int) -> TicketSummary:
    for t in (await ticket_summaries()).tickets:
        if t.id == ticket_id:
            return t
    raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} not found.")


# ---------------------------------------------------------------------------
# 2. Run the agent team on one ticket
# ---------------------------------------------------------------------------


@app.post("/tickets/{ticket_id}/run", response_model=RunTicketResponse)
async def run_ticket(ticket_id: int, body: RunTicketRequest | None = None) -> RunTicketResponse:
    """Boss + team work this ticket to a final decision. Takes ~20-60 seconds."""
    body = body or RunTicketRequest()
    await get_ticket(ticket_id)  # 404 if it doesn't exist
    try:
        budget = TokenBudget(limit_usd=body.approve_budget, approved_by=body.approved_by)
    except BudgetApprovalRequired as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    if desk_lock.locked():
        raise HTTPException(status_code=409, detail="Another agent run is in progress.")
    async with desk_lock:
        result = await run_desk(state["mcp"], state["team"], [ticket_id], budget, run_id=new_run_id())
    decision = result["results"][0] if result["results"] else {"ticket_id": ticket_id, "stopped": "no result"}
    if "stopped" in decision:
        raise HTTPException(status_code=402, detail={"run_id": result["run_id"], **decision, "budget": result["budget"]})
    return RunTicketResponse(run_id=result["run_id"], ticket_id=ticket_id, decision=decision, budget=result["budget"])


@app.post("/tickets/{ticket_id}/resolve", response_model=TicketSummary)
async def resolve_ticket(ticket_id: int, body: ResolveTicketRequest) -> TicketSummary:
    """A named human marks the ticket resolved once the run is done and nothing is waiting on approval."""
    ensure_idle()
    result = await call("human_resolve_ticket", {"ticket_id": ticket_id, "closed_by": body.closed_by, "note": body.note})
    audit.record(run_id=f"human-{new_run_id()[5:]}", agent="human", event="human_resolution", ticket_id=ticket_id,
                 detail={"closed_by": body.closed_by, "note": body.note, "result": result})
    return await get_ticket(ticket_id)


# ---------------------------------------------------------------------------
# 3. Recent agent activity and tools used
# ---------------------------------------------------------------------------


@app.get("/activity", response_model=ActivityResponse)
async def activity(
    runs: int = Query(5, ge=1, le=50, description="How many recent desk runs to summarize."),
    ticket_id: int | None = Query(None, description="Only runs that worked this ticket."),
) -> ActivityResponse:
    """What the agents did in recent runs: who ran, model calls, MCP tools used, delegations, cost, decisions."""
    path = audit.AUDIT_PATH
    entries: list[dict] = json.loads(path.read_text()) if path.exists() and path.stat().st_size else []

    by_run: dict[str, list[dict]] = defaultdict(list)
    for e in entries:
        if e["run_id"].startswith("desk-"):
            by_run[e["run_id"]].append(e)

    summaries: list[RunActivity] = []
    for run_id, events in by_run.items():
        tickets = sorted({e["ticket_id"] for e in events if e.get("ticket_id") is not None})
        if ticket_id is not None and ticket_id not in tickets:
            continue
        agents: dict[str, AgentActivity] = {}
        tools: Counter = Counter()
        refused = 0
        errors: list[str] = []
        for e in events:
            a = agents.setdefault(e["agent"], AgentActivity()) if e["agent"] != "desk" else None
            if e["event"] == "model_response" and a is not None:
                a.model_calls += 1
                a.cost_usd = round(a.cost_usd + e["detail"].get("cost_usd", 0), 6)
                for part in e["detail"].get("parts", []):
                    if part["kind"] == "tool_call" and part["tool"] != "final_result":
                        a.tools[part["tool"]] = a.tools.get(part["tool"], 0) + 1
                        tools[part["tool"]] += 1
            elif e["event"] == "loop_end" and a is not None:
                out = e["detail"].get("output") or {}
                a.summary = out.get("summary") or out.get("decision") or a.summary
            elif e["event"] == "delegation_sent" and a is not None:
                a.delegated_to.append(e["detail"]["to_agent"])
            elif e["event"] == "delegation_refused":
                refused += 1
            elif e["event"] in ("loop_error", "budget_approval_required"):
                errors.append(f"{e['agent']}: {e['detail'].get('error')}")
        end = next((e for e in reversed(events) if e["event"] == "desk_end"), None)
        summaries.append(RunActivity(
            run_id=run_id, started=events[0]["timestamp"], ended=end["timestamp"] if end else None,
            tickets=tickets, agents={k: v for k, v in agents.items() if v.model_calls or v.delegated_to},
            tools_used=dict(tools.most_common()), refused_delegations=refused, errors=errors,
            cost_usd=end["detail"]["budget"]["spent_usd"] if end else None,
            decisions=list(end["detail"]["results"]) if end else [],
        ))
    summaries.sort(key=lambda r: r.started, reverse=True)

    human = [
        {"timestamp": e["timestamp"], "event": e["event"], "agent": e["agent"], "ticket_id": e.get("ticket_id"),
         "detail": e["detail"]}
        for e in entries if e["event"] in ("human_approval", "human_rejection", "payment_executed",
                                           "payment_refused", "db_reset", "human_resolution")
    ][-20:][::-1]
    return ActivityResponse(runs=summaries[:runs], human_actions=human, audit_entries_total=len(entries))


def describe(e: dict) -> str | None:
    """One readable line per audit step, for the live feed. None = skip."""
    d, ev, who = e.get("detail", {}), e["event"], e["agent"].replace("_", " ").title()
    if ev == "loop_start":
        return f"{who} started: {d.get('task', '')[:160]}"
    if ev == "model_response":
        calls = [p for p in d.get("parts", []) if p["kind"] == "tool_call"]
        if not calls:
            return f"{who} is thinking"
        out = []
        for p in calls:
            if p["tool"] == "delegate":
                out.append(f"hands work to {p['args'].get('to_agent', '?').replace('_', ' ').title()}")
            elif p["tool"] == "final_result":
                out.append("writes its report")
            else:
                out.append(f"calls {p['tool']}")
        return f"{who} " + ", ".join(out)
    if ev == "delegation_returned":
        return f"{d.get('from_agent', '?').replace('_', ' ').title()} reported back to {who}"
    if ev == "delegation_refused":
        return f"{who} was refused a hand-off to {d.get('to_agent')}: {d.get('reason')}"
    if ev == "loop_end":
        out = d.get("output") or {}
        return f"{who} finished: {(out.get('summary') or out.get('decision') or '')[:200]}"
    if ev in ("loop_error", "budget_approval_required"):
        return f"{who} stopped: {d.get('error')}"
    if ev == "desk_start" and "tickets_requested" in d:
        return f"Desk run started for ticket(s) {d.get('tickets_requested')}"
    if ev == "desk_end":
        return f"Desk run finished. Tokens: ${d.get('budget', {}).get('spent_usd', 0):.4f}"
    if ev == "human_approval":
        return f"{d.get('approver')} approved request #{d.get('approval', {}).get('approval_request_id')}"
    if ev == "payment_executed":
        p = d.get("payment", {})
        return f"Paid ${p.get('amount', 0):,.2f} to {p.get('payee')}; checking now ${p.get('new_balance', 0):,.2f}"
    if ev == "payment_refused":
        return f"Payment refused: {d.get('error')}"
    if ev == "human_rejection":
        return f"{d.get('approver')} rejected request #{d.get('approval', {}).get('approval_request_id')}"
    if ev == "human_resolution":
        return f"{d.get('closed_by')} marked the ticket resolved"
    if ev == "db_reset":
        return "Database reset to the original seed"
    return None


@app.get("/activity/events", response_model=LiveEventsResponse)
async def live_events(
    after: int = Query(-1, description="Return audit entries after this index. -1 = just the latest `limit`."),
    limit: int = Query(200, ge=1, le=1000),
) -> LiveEventsResponse:
    """Step-by-step feed of what the agents (and humans) are doing, read from the audit trail. Poll it during a run."""
    path = audit.AUDIT_PATH
    entries: list[dict] = json.loads(path.read_text()) if path.exists() and path.stat().st_size else []
    start = max(after + 1, 0) if after >= 0 else max(len(entries) - limit, 0)
    events = []
    for i in range(start, len(entries)):
        e = entries[i]
        text = describe(e)
        if text:
            events.append(LiveEvent(index=i, timestamp=e["timestamp"], run_id=e["run_id"], agent=e["agent"],
                                    event=e["event"], ticket_id=e.get("ticket_id"), depth=e.get("depth", 0), text=text))
    return LiveEventsResponse(events=events[-limit:], next_after=len(entries) - 1, run_in_progress=desk_lock.locked())


# ---------------------------------------------------------------------------
# 4. Human approval -> payment
# ---------------------------------------------------------------------------


@app.get("/approvals")
async def list_approvals(status: str | None = Query(None, description="pending, approved, rejected, or paid")) -> dict:
    """The approval queue (and saved message drafts)."""
    return await call("list_approval_queue", {"status": status} if status else {})


@app.post("/approvals/{approval_id}/approve", response_model=ApproveAndPayResponse)
async def approve_and_pay(approval_id: int, body: ApprovalDecisionRequest) -> ApproveAndPayResponse:
    """A named human approves the request; the pay tool then moves the cash and updates every table."""
    ensure_idle()
    run_id = f"human-{new_run_id()[5:]}"
    approval = await call("human_decide_approval", {"approval_request_id": approval_id, "decision": "approve",
                                      "approver": body.approver, "reason": body.reason})
    audit.record(run_id=run_id, agent="human", event="human_approval", ticket_id=approval["ticket_id"],
                 detail={"approver": body.approver, "reason": body.reason, "approval": approval})

    payment, error = None, None
    try:
        payment = await state["mcp"].direct_call_tool(
            "pay_approved_request", {"approval_request_id": approval_id, "requested_by": "dashboard"})
        audit.record(run_id=run_id, agent="dashboard", event="payment_executed", ticket_id=approval["ticket_id"],
                     detail={"payment": payment})
    except ModelRetry as exc:
        error = str(getattr(exc, "message", exc))
        audit.record(run_id=run_id, agent="dashboard", event="payment_refused", ticket_id=approval["ticket_id"],
                     detail={"approval_request_id": approval_id, "error": error})

    cash = await call("get_cash_position")
    queue = await call("list_approval_queue")
    open_for_ticket = sum(1 for a in queue["approval_requests"]
                          if a["ticket_id"] == approval["ticket_id"] and a["status"] in ("pending", "approved"))
    checking = next((a["balance"] for a in cash["cash_accounts"] if a["name"] == "checking"), None)
    return ApproveAndPayResponse(approval=approval, payment=payment, paid=payment is not None, error=error,
                                 checking_balance=checking, ticket_open_approvals=open_for_ticket)


@app.post("/approvals/{approval_id}/reject")
async def reject(approval_id: int, body: ApprovalDecisionRequest) -> dict:
    """A named human rejects the request. No money moves."""
    ensure_idle()
    result = await call("human_decide_approval", {"approval_request_id": approval_id, "decision": "reject",
                                    "approver": body.approver, "reason": body.reason})
    audit.record(run_id=f"human-{new_run_id()[5:]}", agent="human", event="human_rejection",
                 ticket_id=result["ticket_id"], detail={"approver": body.approver, "reason": body.reason,
                                                        "approval": result})
    return result


# ---------------------------------------------------------------------------
# 5. Cash
# ---------------------------------------------------------------------------


@app.get("/cash/checking", response_model=CheckingBalance)
async def checking_balance() -> CheckingBalance:
    """The cash_accounts checking balance, plus what is already owed against it."""
    cash = await call("get_cash_position")
    acct = next((a for a in cash["cash_accounts"] if a["name"] == "checking"), None)
    if acct is None:
        raise HTTPException(status_code=404, detail="No checking account in cash_accounts.")
    owed = cash["open_invoices_total"] + cash["upcoming_rent_total"] + cash["queued_purchase_orders_total"]
    return CheckingBalance(account="checking", balance=acct["balance"], as_of=acct["date"],
                           open_obligations=owed, free_after_obligations=acct["balance"] - owed)


@app.get("/cash")
async def cash_position() -> dict:
    """Full cash position from get_cash_position: balances, obligations, payments log, approval queue."""
    return await call("get_cash_position")


# ---------------------------------------------------------------------------
# 6. Reset
# ---------------------------------------------------------------------------


@app.post("/reset")
async def reset(body: ResetRequest) -> dict:
    """Back up the database, restore the shop tables from the seed, and clear agent tables."""
    ensure_idle()
    result = await call("human_reset_database", {"confirm": body.confirm})
    audit.record(run_id=f"reset-{new_run_id()[5:]}", agent="dashboard", event="db_reset", detail=result)
    return result
