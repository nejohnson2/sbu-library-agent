"""The agent: a local gemma4 model, one local tool, and (optionally) the SBU NEXUS MCP server."""

import os
from datetime import datetime

from dotenv import load_dotenv
from pydantic_ai import Agent, DeferredToolRequests
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.models.ollama import OllamaModel
from pydantic_ai.providers.ollama import OllamaProvider

from auth import make_auth

load_dotenv()

# 1. The model: gemma4 running in Ollama on this machine.
model = OllamaModel(
    os.getenv("MODEL_NAME", "gemma4"),
    provider=OllamaProvider(base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")),
)

# 2. Remote tools: the NEXUS MCP server, if a URL is configured.
#    Tools that change your library account wait for you to click Approve in the chat.
NEEDS_APPROVAL = {"alma_renew_user_loan", "alma_cancel_user_request"}

nexus = None
toolsets = []
if mcp_url := os.getenv("NEXUS_MCP_URL"):
    # The SSO login happens while connecting, so allow time to log in (default is 5 seconds).
    nexus = MCPToolset(mcp_url, auth=make_auth(mcp_url), init_timeout=300)
    toolsets.append(nexus.approval_required(lambda ctx, tool, args: tool.name in NEEDS_APPROVAL))


# 3. A local tool: any plain Python function the model can choose to call.
#    The docstring becomes the tool description the model sees.
def current_time() -> str:
    """Return the current local date and time."""
    return datetime.now().strftime("%A, %B %d, %Y %I:%M %p")


def today_is() -> str:
    """Added to the instructions so the model always knows today's date."""
    return f"Today is {datetime.now():%A, %B %d, %Y}."


# 4. The agent ties the model, instructions, and tools together.
agent = Agent(
    model,
    instructions=[
        "You are a helpful assistant for Stony Brook University Libraries. "
        "Use your tools to look things up instead of guessing. Keep answers short.",
        today_is,  # a function, so it runs fresh on every request
    ],
    tools=[current_time],  # local tools
    toolsets=toolsets,  # remote tools (NEXUS)
    output_type=[str, DeferredToolRequests],  # DeferredToolRequests = "paused, waiting for approval"
)
