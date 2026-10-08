"""
boss.py

Boss agent: reads every open ticket, decides which agents work on it, sends
them the work, and makes the final decision. It is the only agent that can
record a ticket decision (record_ticket_decision). It never moves money or sends messages.

Routing plan (Problem 6): each ticket type calls the minimum set of agents
needed to close it. The Boss reads the ticket's fact sheet (check_order_fulfillment/2/3)
itself, so it only delegates for things it cannot do: queue money
(accounting, the only agent with request_payment_approval) and write the customer's message
(customer_service). The plan is enforced in the delegate tool, not just in
the prompt: any hand-off outside it is refused and logged.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from pydantic_ai.mcp import MCPToolset

from .base import ShopAgent
from .models import BossDecision, DeskDeps

NAME = "boss"
ROLE = "Reads each ticket, routes it to the right agents, and makes and records the final decision."
MCP_TOOLS = {"check_order_fulfillment", "check_rent_coverage", "price_bulk_order", "list_ticket_queue", "list_approval_queue", "record_ticket_decision"}
CAN_DELEGATE_TO = {"inventory", "accounting", "facilities", "customer_service"}


@dataclass(frozen=True)
class TicketPlan:
    fact_sheet: str
    agents: tuple[str, ...]  # in the order the Boss should call them
    why: str


TICKET_PLANS: dict[str, TicketPlan] = {
    "customer_order": TicketPlan(
        fact_sheet="check_order_fulfillment",
        agents=("accounting", "customer_service"),
        why=(
            "check_order_fulfillment already gives stock for the size, the restock invoice, its vendor and lead days, so inventory adds "
            "no new facts. The restock is held up by an unpaid invoice, which only accounting can queue for approval. "
            "The customer is waiting, so customer_service drafts the reply after the money step is known, offering the "
            "in-stock sizes of the same product."
        ),
    ),
    "rent_notice": TicketPlan(
        fact_sheet="check_rent_coverage",
        agents=("accounting",),
        why=(
            "check_rent_coverage already gives the lease, landlord, rent, due date and cash coverage, so facilities adds no new facts. "
            "Paying rent is money, which only accounting can queue. No customer is involved."
        ),
    ),
    "price_override": TicketPlan(
        fact_sheet="price_bulk_order",
        agents=("accounting", "customer_service"),
        why=(
            "price_bulk_order already gives fillable qty, shortfall, stock by size, cost, price floor and vendors, so inventory adds "
            "no new facts. Accounting decides the discount and whether cash allows a reprint PO; the quote covers only "
            "the quantity fillable now unless the reprint is funded, plus other in-stock sizes of the same product as an "
            "alternative. customer_service drafts the quote for the club."
        ),
    ),
}


class BossAgent(ShopAgent[BossDecision]):
    async def decide(self, ticket: dict, deps: DeskDeps) -> BossDecision:
        plan = TICKET_PLANS.get(ticket["type"])
        if plan:
            deps.allowed_agents = set(plan.agents)
            routing = (
                f"Routing plan for a {ticket['type']} ticket: read {plan.fact_sheet} yourself first, then delegate to "
                f"{' then '.join(plan.agents)} — no other agents. Why: {plan.why}"
            )
        else:
            routing = "No routing plan for this ticket type: call only the agents the decision truly needs."
        followup = ""
        if ticket.get("decision_history"):
            followup = (
                "This is a FOLLOW-UP run: the ticket already has decisions. Check list_approval_queue first; if this ticket's "
                "approval requests are all paid (or rejected) and its draft exists, record 'resolved' with record_ticket_decision "
                "without delegating.\n"
            )
        task = (
            f"Work ticket {ticket['id']} to a final decision. The ticket row from list_ticket_queue is:\n"
            f"{json.dumps(ticket, indent=2, default=str)}\n"
            f"{routing}\n"
            f"{followup}"
            "Collect the reports, record your decision with record_ticket_decision, then return your BossDecision."
        )
        return await self.run_loop(task, deps)


def build(mcp: MCPToolset) -> BossAgent:
    return BossAgent(
        name=NAME,
        role=ROLE,
        output_type=BossDecision,
        mcp=mcp,
        mcp_tools=MCP_TOOLS,
        can_delegate_to=CAN_DELEGATE_TO,
        request_limit=12,
        tool_calls_limit=12,
        max_output_tokens=4_000,
        # One hand-off at a time, so customer_service always gets accounting's exact numbers.
        parallel_tool_calls=False,
    )
