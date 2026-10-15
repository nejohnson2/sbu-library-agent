"""Log in to the NEXUS MCP server and list its tools. Run with: uv run python login.py"""

import asyncio

from agent import nexus


async def main():
    if nexus is None:
        print("Set NEXUS_MCP_URL in .env first.")
        return
    async with nexus:  # opens the browser for SSO login if needed
        for tool in await nexus.client.list_tools():
            print(f"- {tool.name}: {(tool.description or '').splitlines()[0][:80]}")


asyncio.run(main())
