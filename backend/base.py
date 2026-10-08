"""
base.py

ShopAgent: the piece every Campus Customs agent is built from.

Each agent has its own system prompt (backend/prompts/<name>.md), its own
gpt-6-luna model instance, its own MCP tool allowlist, its own list of
agents it may send work to, and its own loop (run_loop) with its own usage
limits. run_loop walks the Pydantic AI graph node by node so that every
model request, model response, tool result and delegation is appended to
output/audit_trail.json, and the token budget is checked before each model
call.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Generic, TypeVar

from pydantic import BaseModel
from pydantic_ai import Agent, RunContext
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.messages import (
    RetryPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import UsageLimits

from . import audit
from .config import MODEL_NAME, PROMPTS, build_model
from .models import DeskDeps

OutputT = TypeVar("OutputT", bound=BaseModel)

MAX_DELEGATION_DEPTH = 2  # boss (0) -> specialist (1) -> specialist (2), no further
MAX_LOGGED_CHARS = 4_000


def _clip(value: Any) -> Any:
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    return text if len(text) <= MAX_LOGGED_CHARS else text[:MAX_LOGGED_CHARS] + "...[truncated]"


class ShopAgent(Generic[OutputT]):
    name: str
    role: str  # one line, shown to other agents when they consider delegating

    def __init__(
        self,
        *,
        name: str,
        role: str,
        output_type: type[OutputT],
        mcp: MCPToolset,
        mcp_tools: set[str],
        can_delegate_to: set[str],
        request_limit: int,
        tool_calls_limit: int,
        max_output_tokens: int = 3_000,
        parallel_tool_calls: bool = True,
    ):
        self.name = name
        self.role = role
        self.mcp_tools = mcp_tools
        self.can_delegate_to = can_delegate_to
        self.usage_limits = UsageLimits(request_limit=request_limit, tool_calls_limit=tool_calls_limit)
        self.prompt_path = PROMPTS / f"{name}.md"

        toolset = mcp.filtered(lambda ctx, tool_def: tool_def.name in self.mcp_tools)
        self.agent: Agent[DeskDeps, OutputT] = Agent(
            build_model(),
            name=name,
            deps_type=DeskDeps,
            output_type=output_type,
            system_prompt=self.prompt_path.read_text(),
            toolsets=[toolset],
            model_settings=ModelSettings(max_tokens=max_output_tokens, parallel_tool_calls=parallel_tool_calls),
            retries=2,
        )
        if can_delegate_to:
            self._register_delegate_tool()

    # ------------------------------------------------------------------
    # Delegation: send work to another agent and get its report back
    # ------------------------------------------------------------------

    def _register_delegate_tool(self) -> None:
        targets = ", ".join(sorted(self.can_delegate_to))

        @self.agent.tool
        async def delegate(ctx: RunContext[DeskDeps], to_agent: str, task: str) -> dict:
            """Send a specific task to another agent and wait for its structured report.

            to_agent must be one of the agents you are allowed to delegate to. task
            should name the ticket id and say exactly what you need back.
            """
            deps = ctx.deps
            refusal = None
            if to_agent not in self.can_delegate_to:
                refusal = f"{self.name} may only delegate to: {targets}."
            elif deps.allowed_agents is not None and to_agent not in deps.allowed_agents:
                refusal = (
                    f"{to_agent} is not in the routing plan for ticket {deps.ticket_id} "
                    f"({', '.join(sorted(deps.allowed_agents))}). Finish with your own tools or report the gap."
                )
            elif to_agent in deps.chain:
                refusal = f"{to_agent} is already working on this request upstream ({' -> '.join(deps.chain)}); no loops."
            elif deps.depth >= MAX_DELEGATION_DEPTH:
                refusal = f"Delegation depth limit ({MAX_DELEGATION_DEPTH}) reached. Do the work yourself or report back."
            if refusal:
                audit.record(
                    run_id=deps.run_id, agent=self.name, event="delegation_refused", ticket_id=deps.ticket_id,
                    depth=deps.depth, chain=deps.chain, detail={"to_agent": to_agent, "task": task, "reason": refusal},
                )
                return {"refused": True, "reason": refusal}

            audit.record(
                run_id=deps.run_id, agent=self.name, event="delegation_sent", ticket_id=deps.ticket_id,
                depth=deps.depth, chain=deps.chain, detail={"to_agent": to_agent, "task": task},
            )
            report = await deps.team[to_agent].run_loop(task, deps.child(to_agent))
            audit.record(
                run_id=deps.run_id, agent=self.name, event="delegation_returned", ticket_id=deps.ticket_id,
                depth=deps.depth, chain=deps.chain, detail={"from_agent": to_agent, "report": report.model_dump()},
            )
            return report.model_dump()

        roster = "\n".join(f"- {n}: {r}" for n, r in sorted(self._roster().items()))
        self.agent.system_prompt(lambda: f"Agents you may delegate to with the `delegate` tool:\n{roster}")

    def _roster(self) -> dict[str, str]:
        from .team import AGENT_ROLES

        return {n: AGENT_ROLES[n] for n in self.can_delegate_to}

    # ------------------------------------------------------------------
    # The agent loop
    # ------------------------------------------------------------------

    async def run_loop(self, task: str, deps: DeskDeps) -> OutputT:
        loop_id = f"{self.name}-{uuid.uuid4().hex[:8]}"
        chain = deps.chain or [self.name]
        deps.chain = chain
        log = lambda event, step=None, **detail: audit.record(  # noqa: E731
            run_id=deps.run_id, loop_id=loop_id, agent=self.name, event=event, ticket_id=deps.ticket_id,
            depth=deps.depth, chain=chain, step=step, detail=detail,
        )

        log(
            "loop_start", task=task, model=MODEL_NAME, prompt_file=str(self.prompt_path.name),
            mcp_tools=sorted(self.mcp_tools), can_delegate_to=sorted(self.can_delegate_to),
            usage_limits={"request_limit": self.usage_limits.request_limit,
                          "tool_calls_limit": self.usage_limits.tool_calls_limit},
        )
        step = 0
        last_input_tokens: int | None = None
        counted_in = counted_out = counted_req = 0
        try:
            async with self.agent.iter(task, deps=deps, usage_limits=self.usage_limits) as run:
                async for node in run:
                    step += 1
                    if Agent.is_model_request_node(node):
                        projected = deps.budget.check(last_input_tokens)
                        log("model_request", step, parts=self._request_parts(node.request.parts),
                            projected_spend_usd=round(projected, 6))
                    elif Agent.is_call_tools_node(node):
                        usage = run.usage
                        d_in = usage.input_tokens - counted_in
                        d_out = usage.output_tokens - counted_out
                        d_req = usage.requests - counted_req
                        counted_in, counted_out, counted_req = usage.input_tokens, usage.output_tokens, usage.requests
                        cost = deps.budget.add(self.name, d_in, d_out, d_req)
                        last_input_tokens = d_in or last_input_tokens
                        log("model_response", step, parts=self._response_parts(node.model_response.parts),
                            input_tokens=d_in, output_tokens=d_out, cost_usd=round(cost, 6),
                            run_spend_usd=round(deps.budget.spent_usd, 6))
                    elif Agent.is_end_node(node):
                        pass
                result = run.result
            assert result is not None
            output = result.output
            log("loop_end", step, output=output.model_dump(), steps=step,
                tokens={"input": counted_in, "output": counted_out, "requests": counted_req})
            return output
        except Exception as exc:
            event = "budget_approval_required" if type(exc).__name__ == "BudgetApprovalRequired" else "loop_error"
            log(event, step, error=f"{type(exc).__name__}: {exc}", budget=deps.budget.snapshot())
            raise

    @staticmethod
    def _request_parts(parts: Any) -> list[dict]:
        out = []
        for p in parts:
            if isinstance(p, UserPromptPart):
                out.append({"kind": "user_prompt", "content": _clip(p.content)})
            elif isinstance(p, ToolReturnPart):
                out.append({"kind": "tool_result", "tool": p.tool_name, "content": _clip(p.content)})
            elif isinstance(p, RetryPromptPart):
                out.append({"kind": "retry", "tool": p.tool_name, "content": _clip(p.content)})
        return out

    @staticmethod
    def _response_parts(parts: Any) -> list[dict]:
        out = []
        for p in parts:
            if isinstance(p, ToolCallPart):
                out.append({"kind": "tool_call", "tool": p.tool_name, "args": p.args_as_dict()})
            elif isinstance(p, TextPart) and p.content.strip():
                out.append({"kind": "text", "content": _clip(p.content)})
        return out
