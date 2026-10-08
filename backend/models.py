"""
models.py

Data types shared by the Campus Customs agent team: agent names, the
structured outputs each agent returns, the dependencies passed through every
agent loop, and the shape of an audit-trail entry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from .budget import TokenBudget
    from .base import ShopAgent

AgentName = Literal["boss", "inventory", "accounting", "facilities", "customer_service"]
TicketStatus = Literal["in_progress", "awaiting_approval", "resolved"]


# ---------------------------------------------------------------------------
# Structured outputs
# ---------------------------------------------------------------------------


class Fact(BaseModel):
    """One shop fact the agent relied on, with the MCP tool it came from."""

    name: str = Field(description="What the fact is, e.g. 'CC-TEE-WHITE S qty on hand'.")
    value: str = Field(description="The value exactly as the tool returned it.")
    source_tool: str = Field(description="MCP tool that returned it, e.g. 'lookup_inventory_pricing'.")


class DraftRef(BaseModel):
    draft_id: int
    audience: Literal["customer", "vendor", "landlord"]
    recipient: str
    subject: str
    body: str


class SpecialistReport(BaseModel):
    """What Inventory, Accounting, Facilities, and Customer Service hand back."""

    agent: AgentName
    ticket_id: int | None = None
    summary: str = Field(description="2-4 sentence plain-English answer to the task you were given.")
    facts: list[Fact] = Field(default_factory=list, description="Every number or status you used, with its source tool.")
    actions_taken: list[str] = Field(default_factory=list, description="Database writes you made via MCP (approval requests, drafts).")
    approval_request_ids: list[int] = Field(default_factory=list, description="IDs returned by request_payment_approval. Empty if none.")
    drafts: list[DraftRef] = Field(default_factory=list, description="Drafts saved via save_message_draft. Empty if none.")
    recommendations: list[str] = Field(default_factory=list, description="What you recommend the Boss decide.")
    needs_human: list[str] = Field(default_factory=list, description="Anything only a human can do (approve money, send a message).")
    blockers: list[str] = Field(default_factory=list, description="Anything that stopped you, e.g. not enough cash.")


class BossDecision(BaseModel):
    """The Boss's final decision on one ticket."""

    ticket_id: int
    ticket_type: str
    assigned_agents: list[AgentName] = Field(description="Agents the Boss sent work to, in order.")
    decision: str = Field(description="The final decision in 2-5 sentences, citing the key numbers.")
    ticket_status: TicketStatus
    reasons: list[str] = Field(description="Why, each reason tied to a fact from an agent report or MCP tool.")
    approval_request_ids: list[int] = Field(default_factory=list, description="Pending approvals for this ticket.")
    draft_ids: list[int] = Field(default_factory=list, description="Message drafts for this ticket (never sent).")
    human_actions_needed: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list, description="Cash, stock, or timing risks the owner should know about.")


# ---------------------------------------------------------------------------
# Run-time dependencies
# ---------------------------------------------------------------------------


@dataclass
class DeskDeps:
    """Passed into every agent loop. Delegation creates a child copy with depth + 1."""

    run_id: str
    ticket_id: int | None
    budget: "TokenBudget"
    team: dict[str, "ShopAgent"]
    depth: int = 0
    chain: list[str] = field(default_factory=list)
    allowed_agents: set[str] | None = None  # the ticket's routing plan; None = no restriction

    def child(self, agent_name: str) -> "DeskDeps":
        return DeskDeps(
            run_id=self.run_id,
            ticket_id=self.ticket_id,
            budget=self.budget,
            team=self.team,
            depth=self.depth + 1,
            chain=[*self.chain, agent_name],
            allowed_agents=self.allowed_agents,
        )


# ---------------------------------------------------------------------------
# Audit trail
# ---------------------------------------------------------------------------

AuditEvent = Literal[
    "desk_start",
    "ticket_queue_read",
    "desk_end",
    "loop_start",
    "model_request",
    "model_response",
    "tool_result",
    "delegation_sent",
    "delegation_returned",
    "delegation_refused",
    "loop_end",
    "loop_error",
    "budget_check",
    "budget_approval_required",
    # human / dashboard actions through the FastAPI backend (Problem 7)
    "human_approval",
    "human_rejection",
    "payment_executed",
    "payment_refused",
    "db_reset",
    "human_resolution",
]


class AuditEntry(BaseModel):
    timestamp: str
    run_id: str
    loop_id: str | None = None
    agent: str
    event: AuditEvent
    ticket_id: int | None = None
    depth: int = 0
    chain: list[str] = Field(default_factory=list)
    step: int | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# FastAPI request / response bodies (Problem 7, backend/main.py)
# ---------------------------------------------------------------------------


class TicketSummary(BaseModel):
    id: int
    type: str
    requester: str
    subject: str
    notes: str | None = None
    sku: str | None = None
    size: str | None = None
    qty: int | None = None
    created_at: str | None = None
    status: str = Field(description="Raw tickets.status: open, in_progress, awaiting_approval, or resolved.")
    open_or_closed: Literal["open", "closed"] = Field(description="'closed' only when status is 'resolved'.")
    pending_approval_ids: list[int] = Field(default_factory=list)
    draft_ids: list[int] = Field(default_factory=list)
    last_decision: str | None = None
    last_decided_at: str | None = None


class TicketsResponse(BaseModel):
    today: str
    tickets: list[TicketSummary]


class RunTicketRequest(BaseModel):
    approve_budget: float = Field(0.50, description="Token budget in USD. Above $0.50 needs approved_by.")
    approved_by: str | None = Field(None, description="Human approving a token budget above $0.50.")


class RunTicketResponse(BaseModel):
    run_id: str
    ticket_id: int
    decision: dict[str, Any]
    budget: dict[str, Any]


class ApprovalDecisionRequest(BaseModel):
    approver: str = Field(description="The human's name. Agent names are refused.")
    reason: str = ""


class ApproveAndPayResponse(BaseModel):
    approval: dict[str, Any]
    payment: dict[str, Any] | None = None
    paid: bool
    error: str | None = None
    checking_balance: float | None = None
    ticket_open_approvals: int | None = None


class CheckingBalance(BaseModel):
    account: str
    balance: float
    as_of: str
    open_obligations: float
    free_after_obligations: float


class ResolveTicketRequest(BaseModel):
    closed_by: str = Field(description="The human marking the ticket resolved. Agent names are refused.")
    note: str = ""


class LiveEvent(BaseModel):
    index: int = Field(description="Position in audit_trail.json; pass the last one back as ?after=.")
    timestamp: str
    run_id: str
    agent: str
    event: str
    ticket_id: int | None
    depth: int
    text: str = Field(description="One-line human-readable description of the step.")


class LiveEventsResponse(BaseModel):
    events: list[LiveEvent]
    next_after: int
    run_in_progress: bool


class ResetRequest(BaseModel):
    confirm: str = Field(description="Must be exactly 'RESET'.")


class AgentActivity(BaseModel):
    summary: str | None = Field(None, description="The agent's last report summary (or the Boss's decision) in this run.")
    model_calls: int = 0
    tools: dict[str, int] = Field(default_factory=dict)
    delegated_to: list[str] = Field(default_factory=list)
    cost_usd: float = 0.0


class RunActivity(BaseModel):
    run_id: str
    started: str
    ended: str | None
    tickets: list[int]
    agents: dict[str, AgentActivity]
    tools_used: dict[str, int]
    refused_delegations: int
    errors: list[str]
    cost_usd: float | None
    decisions: list[dict[str, Any]]


class ActivityResponse(BaseModel):
    runs: list[RunActivity]
    human_actions: list[dict[str, Any]]
    audit_entries_total: int
