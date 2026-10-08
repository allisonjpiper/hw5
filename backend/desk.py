"""
desk.py

One desk run: read the ticket queue over MCP, then have the Boss work each
ticket to a final decision with the rest of the team. Shared by the FastAPI
backend (main.py) and the command line (cli.py).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic_ai.mcp import MCPToolset

from . import audit
from .base import ShopAgent
from .budget import BudgetApprovalRequired, TokenBudget
from .models import DeskDeps


def new_run_id() -> str:
    return f"desk-{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:4]}"


async def run_desk(
    mcp: MCPToolset,
    team: dict[str, ShopAgent],
    ticket_ids: list[int] | None,
    budget: TokenBudget,
    run_id: str | None = None,
) -> dict:
    """Work the given tickets (or every unresolved ticket) and return the Boss's decisions."""
    run_id = run_id or new_run_id()
    boss = team["boss"]
    results: list[dict] = []

    audit.record(run_id=run_id, agent="desk", event="desk_start",
                 detail={"tickets_requested": ticket_ids, "budget": budget.snapshot()})
    async with mcp:
        # A specific ticket can be re-run even after it was resolved.
        queue = await mcp.direct_call_tool("list_ticket_queue", {"include_resolved": ticket_ids is not None})
        tickets = [t for t in queue["tickets"] if ticket_ids is None or t["id"] in ticket_ids]
        audit.record(run_id=run_id, agent="desk", event="ticket_queue_read",
                     detail={"source": "list_ticket_queue", "today": queue["today"], "ticket_ids": [t["id"] for t in tickets]})
        for ticket in tickets:
            deps = DeskDeps(run_id=run_id, ticket_id=ticket["id"], budget=budget, team=team)
            try:
                decision = await boss.decide(ticket, deps)
                results.append(decision.model_dump())
            except BudgetApprovalRequired as exc:
                results.append({"ticket_id": ticket["id"], "stopped": str(exc)})
                break

    audit.record(run_id=run_id, agent="desk", event="desk_end",
                 detail={"results": results, "budget": budget.snapshot()})
    return {"run_id": run_id, "results": results, "budget": budget.snapshot()}
