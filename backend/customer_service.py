"""
customer_service.py

Customer Service agent: writes the messages that go out to customers about
their tickets. Every message is saved as a draft via save_message_draft and never sent.
It checks stock and price facts (directly or via Inventory / Accounting)
before promising anything.
"""

from __future__ import annotations

from pydantic_ai.mcp import MCPToolset

from .base import ShopAgent
from .models import SpecialistReport

NAME = "customer_service"
ROLE = "Writes customer-facing messages about tickets and saves them as drafts (never sent); confirms facts before promising anything."
MCP_TOOLS = {"check_order_fulfillment", "price_bulk_order", "list_ticket_queue", "lookup_inventory_pricing", "save_message_draft", "list_approval_queue"}
CAN_DELEGATE_TO = {"accounting", "boss", "facilities", "inventory"}  # full connectivity; the ticket routing plan narrows it per run


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
