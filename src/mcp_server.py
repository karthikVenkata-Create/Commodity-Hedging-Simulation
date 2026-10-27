"""
MCP server: the same five tools, exposed over the Model Context Protocol.

ai_analyst.py runs its own loop against the API. This file does the other half:
any MCP client (Claude Desktop, Claude Code) can plug into the hedging engine and
call the tools itself, with no API key in this repo. See the README for the
Claude Desktop config.

    python src/mcp_server.py      # speaks MCP over stdio
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp.server.mcpserver import MCPServer  # noqa: E402
from mcp.server.mcpserver.exceptions import ToolError  # noqa: E402

import ai_tools  # noqa: E402

server = MCPServer(
    "hedging-analyst",
    instructions=(
        "Tools for Karthik's Fall 2025 commodity hedging game (7 settled rounds, 100,000 units per round). "
        "Use the tools for every number; they return differences so no arithmetic is needed."
    ),
)


def _call(name, **kwargs):
    args = {k: v for k, v in kwargs.items() if v is not None}
    out, is_error = ai_tools.run_tool(name, args)
    if is_error:
        raise ToolError(out)   # deliberate error: the message reaches the model so it can fix the call
    return out


@server.tool(description=ai_tools.TOOLS[0]["description"])
def get_round(round: int) -> dict:
    return _call("get_round", round=round)


@server.tool(description=ai_tools.TOOLS[1]["description"])
def portfolio_summary() -> dict:
    return _call("portfolio_summary")


@server.tool(description=ai_tools.TOOLS[2]["description"])
def evaluate_hedge(round: int, swap_qty: int | None = None, collar_qty: int | None = None,
                   put_strike: float | None = None, call_strike: float | None = None,
                   sigma: float | None = None) -> dict:
    return _call("evaluate_hedge", round=round, swap_qty=swap_qty, collar_qty=collar_qty,
                 put_strike=put_strike, call_strike=call_strike, sigma=sigma)


@server.tool(description=ai_tools.TOOLS[3]["description"])
def price_collar(round: int, put_strike: float, call_strike: float, sigma: float | None = None) -> dict:
    return _call("price_collar", round=round, put_strike=put_strike, call_strike=call_strike, sigma=sigma)


@server.tool(description=ai_tools.TOOLS[4]["description"])
def memo_search(query: str, round: int | None = None, top_k: int = 3) -> dict:
    return _call("memo_search", query=query, round=round, top_k=top_k)


if __name__ == "__main__":
    server.run("stdio")
