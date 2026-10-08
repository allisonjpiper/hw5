"""
team.py

Builds the five-agent team around one shared MCP connection.

Delegation is fully connected: every agent can send work to every other
agent with the `delegate` tool (the Boss to all four specialists, and each
specialist to the Boss and the other three). On each run the Boss's routing
plan (TICKET_PLANS in boss.py) narrows who is actually reachable for that
ticket, and the delegate tool refuses loops and depth over 2.
"""

from __future__ import annotations

from pydantic_ai.mcp import MCPToolset

from . import accounting, boss, customer_service, facilities, inventory
from .base import ShopAgent

MODULES = (boss, inventory, accounting, facilities, customer_service)
AGENT_ROLES = {m.NAME: m.ROLE for m in MODULES}


def build_team(mcp: MCPToolset) -> dict[str, ShopAgent]:
    return {m.NAME: m.build(mcp) for m in MODULES}
