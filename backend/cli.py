"""
cli.py

Command-line desk run (the FastAPI backend in main.py does the same thing
over HTTP).

    .venv/bin/python -m backend.cli                  # all open tickets
    .venv/bin/python -m backend.cli --ticket 101     # one ticket
    .venv/bin/python -m backend.cli --approve-budget 1.00 --approved-by "Allison Piper"

Token spend is capped at $0.50 per run unless a human raises it by name.
"""

from __future__ import annotations

import argparse
import asyncio
import json

from .budget import DEFAULT_LIMIT_USD, TokenBudget
from .config import build_mcp_toolset
from .desk import run_desk
from .team import build_team


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Campus Customs agent desk.")
    parser.add_argument("--ticket", type=int, action="append", help="Ticket id to work (repeatable). Default: all open.")
    parser.add_argument("--approve-budget", type=float, default=DEFAULT_LIMIT_USD,
                        help=f"Token budget in USD. Above ${DEFAULT_LIMIT_USD:.2f} requires --approved-by.")
    parser.add_argument("--approved-by", help="Name of the human approving a budget above the default.")
    args = parser.parse_args()

    budget = TokenBudget(limit_usd=args.approve_budget, approved_by=args.approved_by)
    mcp = build_mcp_toolset()
    result = asyncio.run(run_desk(mcp, build_team(mcp), args.ticket, budget))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
