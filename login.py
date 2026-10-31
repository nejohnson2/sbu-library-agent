"""Connect to the MCP servers and list their tools. Run with: uv run python login.py

Opens the browser for the NEXUS SSO login if needed, and starts the local PubMed server."""

import asyncio

from agent import nexus, pubmed


async def main():
    servers = [("NEXUS", nexus), ("PubMed", pubmed)]
    if all(s is None for _, s in servers):
        print("Set NEXUS_MCP_URL and/or PUBMED_MCP_DIR in .env first.")
        return
    for name, server in servers:
        if server is None:
            print(f"{name}: not configured")
            continue
        print(f"{name}:")
        async with server:  # NEXUS: opens the browser for SSO login if needed
            for tool in await server.client.list_tools():
                print(f"- {tool.name}: {(tool.description or '').strip().splitlines()[0][:80]}")


asyncio.run(main())
