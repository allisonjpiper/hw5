"""
accounting.py

Accounting agent: owns cash, invoices, margins, and payments. It is the only
agent with the approval-request tool (request_payment_approval) and the pay tool (pay_approved_request).
It queues payments and purchase orders for human approval; it can never
approve one itself, and the pay tool refuses anything not human-approved or
that would take the balance below zero.
"""

from __future__ import annotations

from pydantic_ai.mcp import MCPToolset

from .base import ShopAgent
from .models import SpecialistReport

NAME = "accounting"
ROLE = "Owns cash, invoices, margins, discount floors and payments; the only agent that can queue payments/POs for human approval or run the pay tool."
MCP_TOOLS = {"check_rent_coverage", "price_bulk_order", "lookup_inventory_pricing", "list_vendors_invoices", "get_cash_position", "request_payment_approval", "pay_approved_request", "list_approval_queue"}
CAN_DELEGATE_TO = {"boss", "customer_service", "facilities", "inventory"}  # full connectivity; the ticket routing plan narrows it per run


def build(mcp: MCPToolset) -> ShopAgent[SpecialistReport]:
    return ShopAgent(
        name=NAME,
        role=ROLE,
        output_type=SpecialistReport,
        mcp=mcp,
        mcp_tools=MCP_TOOLS,
        can_delegate_to=CAN_DELEGATE_TO,
        request_limit=12,
        tool_calls_limit=12,
    )
