"""Write the tool descriptions and argument schemas advertised by the NEXUS MCP server to docs/mcp_tools.md.
Run with: uv run python dump_tools.py

This is exactly what the model sees: the server's `tools/list` reply, unedited."""

import asyncio
import json
import logging
from datetime import date
from pathlib import Path

from agent import nexus

OUT = Path(__file__).parent / "docs" / "mcp_tools.md"
log = logging.getLogger("dump_tools")


def _schema(tool) -> dict:
    return getattr(tool, "input_schema", None) or tool.inputSchema  # MCP SDK v2 renamed the field


def _params(schema: dict) -> str:
    props = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    lines = ["| Parameter | Required | Description |", "|---|---|---|"]
    for name, spec in props.items():
        desc = (spec.get("description") or "").replace("\n", " ").replace("|", "\\|")
        lines.append(f"| `{name}` | {'yes' if name in required else 'no'} | {desc} |")
    return "\n".join(lines)


async def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    for noisy in ("httpx", "httpx2", "mcp", "fastmcp"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    parts = [f"# MCP tool descriptions\n\nAs advertised by each server's `tools/list` reply on {date.today()}. "
             "This text is sent to the model with every request; nothing here is written by this project.\n"]
    for server_name, server in (("NEXUS (Clarivate)", nexus),):
        if server is None:
            log.warning("%s not configured, skipping", server_name)
            continue
        async with server:
            tools = await server.client.list_tools()
        log.info("%s: %d tools", server_name, len(tools))
        parts.append(f"\n## {server_name}\n")
        parts.append("Tools: " + ", ".join(f"`{t.name}`" for t in tools) + "\n")
        for t in tools:
            parts.append(f"\n### `{t.name}`\n\n{(t.description or '').strip()}\n")
            parts.append("\n**Parameters**\n\n" + _params(_schema(t)) + "\n")
            parts.append("\n<details><summary>Full JSON Schema</summary>\n\n```json\n"
                         + json.dumps(_schema(t), indent=2) + "\n```\n\n</details>\n")
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text("\n".join(parts))
    log.info("wrote %s", OUT)


asyncio.run(main())
