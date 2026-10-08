"""
inventory.py

Inventory agent: checks stock per sku/size, measures shortfalls, and works
out restocks with vendors (lead days, reprint cost). Saves vendor drafts but
never sends them, and hands anything that costs money to Accounting.
"""

from __future__ import annotations

from pydantic_ai.mcp import MCPToolset

from .base import ShopAgent
from .models import SpecialistReport

NAME = "inventory"
ROLE = "Checks stock by sku/size, measures shortfalls, plans restocks with vendors (lead days, reprint cost), drafts vendor messages."
MCP_TOOLS = {"check_order_fulfillment", "price_bulk_order", "lookup_inventory_pricing", "list_vendors_invoices", "save_message_draft", "list_approval_queue"}
CAN_DELEGATE_TO = {"accounting", "boss", "customer_service", "facilities"}  # full connectivity; the ticket routing plan narrows it per run


def build(mcp: MCPToolset) -> ShopAgent[SpecialistReport]:
    return ShopAgent(
        name=NAME,
        role=ROLE,
        output_type=SpecialistReport,
        mcp=mcp,
        mcp_tools=MCP_TOOLS,
        can_delegate_to=CAN_DELEGATE_TO,
        request_limit=10,
        tool_calls_limit=10,
    )
