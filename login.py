"""Log in to the NEXUS MCP server, list its tools, and save their schemas to nexus_tools.json.
Run with: uv run python login.py

Opens the browser for the NEXUS SSO login if needed. The saved file holds only the tool
names, descriptions and input schemas (what any MCP client sees), so that code reviews can
check the prompt against the real tool contract without connecting to NEXUS."""

import asyncio
import json
from datetime import date
from pathlib import Path

from agent import nexus

SCHEMA_FILE = Path(__file__).parent / "nexus_tools.json"


async def main():
    if nexus is None:
        print("Set NEXUS_MCP_URL in .env first.")
        return
    async with nexus:  # opens the browser for SSO login if needed
        tools = await nexus.client.list_tools()
    for tool in tools:
        print(f"- {tool.name}: {(tool.description or '').strip().splitlines()[0][:80]}")
    SCHEMA_FILE.write_text(json.dumps({
        "generated": date.today().isoformat(),
        "tools": [{"name": t.name, "description": t.description, "input_schema": t.input_schema} for t in tools],
    }, indent=1))
    print(f"\nSaved {len(tools)} tool schemas to {SCHEMA_FILE.name}")


asyncio.run(main())
