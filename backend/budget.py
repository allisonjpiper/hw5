"""
budget.py

Token-spend guard. A desk run may spend up to $0.50 on model tokens without
a human. Before every model request the projected spend is checked; if it
would pass the approved limit, the run stops and asks a human to rerun with
a higher, named approval (see main.py --approve-budget / --approved-by).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from genai_prices import Usage, calc_price

from .config import MODEL_NAME

DEFAULT_LIMIT_USD = 0.50

# Fallback per-million-token prices if genai_prices does not know the model.
FALLBACK_INPUT_PER_M = 0.20
FALLBACK_OUTPUT_PER_M = 0.75

# Worst-case guess for the next request when we have no history yet.
FIRST_REQUEST_INPUT_TOKENS = 6_000
NEXT_REQUEST_OUTPUT_TOKENS = 2_000


class BudgetApprovalRequired(RuntimeError):
    """Raised when the next model call would push spend past the approved limit."""


def cost_usd(input_tokens: int, output_tokens: int) -> float:
    try:
        price = calc_price(
            Usage(input_tokens=input_tokens, output_tokens=output_tokens),
            model_ref=MODEL_NAME,
            provider_id="openai",
        )
        return float(price.total_price)
    except Exception:
        return (input_tokens * FALLBACK_INPUT_PER_M + output_tokens * FALLBACK_OUTPUT_PER_M) / 1_000_000


@dataclass
class TokenBudget:
    limit_usd: float = DEFAULT_LIMIT_USD
    approved_by: str | None = None  # a human name when limit_usd > DEFAULT_LIMIT_USD
    spent_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    requests: int = 0
    by_agent: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.limit_usd > DEFAULT_LIMIT_USD and not (self.approved_by or "").strip():
            raise BudgetApprovalRequired(
                f"A token budget above ${DEFAULT_LIMIT_USD:.2f} needs a named human approver (approved_by / --approved-by)."
            )

    def projected_next(self, last_input_tokens: int | None) -> float:
        in_tokens = (last_input_tokens or FIRST_REQUEST_INPUT_TOKENS) + 1_500
        return self.spent_usd + cost_usd(in_tokens, NEXT_REQUEST_OUTPUT_TOKENS)

    def check(self, last_input_tokens: int | None) -> float:
        projected = self.projected_next(last_input_tokens)
        if projected > self.limit_usd:
            raise BudgetApprovalRequired(
                f"Next model call would bring token spend to about ${projected:.4f}, over the approved "
                f"${self.limit_usd:.2f}. A human must approve a higher budget before agents continue."
            )
        return projected

    def add(self, agent: str, input_tokens: int, output_tokens: int, requests: int) -> float:
        cost = cost_usd(input_tokens, output_tokens)
        self.spent_usd += cost
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.requests += requests
        self.by_agent[agent] = self.by_agent.get(agent, 0.0) + cost
        return cost

    def snapshot(self) -> dict:
        return {
            "limit_usd": self.limit_usd,
            "approved_by": self.approved_by,
            "spent_usd": round(self.spent_usd, 6),
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "requests": self.requests,
            "by_agent_usd": {k: round(v, 6) for k, v in self.by_agent.items()},
        }
