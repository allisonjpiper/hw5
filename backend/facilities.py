"""
facilities.py

Facilities agent: the shop space. Reads leases, rent amounts and due dates,
checks whether rent can be covered, and drafts landlord messages (never
sent). Rent payments go to Accounting to queue for human approval.
"""

from __future__ import annotations

from pydantic_ai.mcp import MCPToolset

from .base import ShopAgent
from .models import SpecialistReport

NAME = "facilities"
ROLE = "Handles the shop space: leases, landlord, rent amount and due dates, rent coverage; drafts landlord messages."
MCP_TOOLS = {"check_rent_coverage", "get_cash_position", "save_message_draft", "list_approval_queue"}
CAN_DELEGATE_TO = {"accounting", "boss", "customer_service", "inventory"}  # full connectivity; the ticket routing plan narrows it per run


def build(mcp: MCPToolset) -> ShopAgent[SpecialistReport]:
    return ShopAgent(
        name=NAME,
        role=ROLE,
        output_type=SpecialistReport,
        mcp=mcp,
        mcp_tools=MCP_TOOLS,
        can_delegate_to=CAN_DELEGATE_TO,
        request_limit=8,
        tool_calls_limit=8,
    )
