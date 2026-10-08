"""
config.py

Paths, the Portkey-backed model (gpt-6-luna only, as the assignment requires), and the
single MCP connection every agent shares. Agents get facts only through
MCP; there is no direct database access anywhere in backend/.
"""

from __future__ import annotations

import os

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

from pathlib import Path

from dotenv import find_dotenv, load_dotenv
from fastmcp.client import Client
from fastmcp.client.transports import StdioTransport
from openai import AsyncOpenAI
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider

BACKEND = Path(__file__).resolve().parent
PROJECT = BACKEND.parent
PROMPTS = BACKEND / "prompts"
MCP_SERVER = PROJECT / "mcp_server" / "server.py"
VENV_PYTHON = PROJECT / ".venv" / "bin" / "python"

load_dotenv(PROJECT / ".env")
load_dotenv(find_dotenv(usecwd=True))
load_dotenv(PROJECT.parent / ".env")  # root .env with PORTKEY_API_KEY

MODEL_NAME = "gpt-6-luna"
PORTKEY_BASE_URL = "https://api.portkey.ai/v1"


def build_model() -> OpenAIResponsesModel:
    """A fresh gpt-6-luna model through Portkey. Each agent gets its own instance.

    Uses OpenAI's Responses API: gpt-6-luna rejects function tools with reasoning
    on /v1/chat/completions, and the agents need both tools and reasoning.
    """
    api_key = os.getenv("PORTKEY_API_KEY")
    if not api_key:
        raise RuntimeError("PORTKEY_API_KEY is missing from the root .env file.")
    client = AsyncOpenAI(
        api_key=api_key,
        base_url=PORTKEY_BASE_URL,
        default_headers={"x-portkey-api-key": api_key},
    )
    return OpenAIResponsesModel(MODEL_NAME, provider=OpenAIProvider(openai_client=client))


def build_mcp_toolset() -> MCPToolset:
    """One stdio connection to mcp_server/server.py, shared and filtered per agent."""
    env = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "CAMPUS_CUSTOMS_DB")}
    transport = StdioTransport(command=str(VENV_PYTHON), args=[str(MCP_SERVER)], env=env, cwd=str(PROJECT))
    # 'retry' hands server-side validation errors (e.g. "would overdraw") back to the model.
    return MCPToolset(Client(transport), id="campus-customs", tool_error_behavior="retry")
