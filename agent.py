"""The agent: a model (local Ollama or the LiteLLM gateway), one local tool, and up to two MCP
servers: the SBU NEXUS server (library catalog and account) and a local PubMed server."""

import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from fastmcp.client.transports import PythonStdioTransport
from pydantic_ai import Agent, DeferredToolRequests
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.models.ollama import OllamaModel
from pydantic_ai.providers.ollama import OllamaProvider

from auth import make_auth

load_dotenv()

INSTRUCTIONS = """\
You are a helpful assistant for Stony Brook University Libraries. Keep answers short.

Rules:
- Use your tools to look things up. Never guess or predict what the library has.
- Searching is read-only, so search right away. Never ask permission first.
- For a list of items (such as a reading list), run a separate primo_search for each
  item, using the title and author fields.
- If a search finds nothing, try once more with just the main title words before
  saying "not found".
- Report only what the search results show.
- Search results do not show whether a print copy is on the shelf. Say whether the
  item is held in print or online, and include its "Record full view" link so the
  user can check.

PubMed (biomedical and life-science journal articles):
- For questions about research articles, studies or clinical literature, use the PubMed
  tools: search_articles first (keep max_results at 5 or fewer unless asked for more),
  then get_article_summaries on the returned PMIDs to get titles, authors, journal and
  date. Use download_article with format_type "abstract" and return_mode "text" only
  when the user wants an abstract.
- PubMed is an index, not the library's collection. When the user asks whether the
  library has an article you found in PubMed, run primo_search with its title.
- Cite each article as: title, first author, journal, year, PMID.
"""

# 1. The model: local Ollama, or the library's remote LiteLLM gateway (set LLM in .env).
#    Both speak the same OpenAI-style API, so one model class works for either.
if os.getenv("LLM", "ollama") == "litellm":
    model_name = os.environ["LITELLM_MODEL"]
    provider = OllamaProvider(base_url=os.environ["LITELLM_BASE_URL"], api_key=os.environ["LITELLM_API_KEY"])
else:
    model_name = os.getenv("OLLAMA_MODEL", "gemma4")
    provider = OllamaProvider(base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"))
model = OllamaModel(model_name, provider=provider)

# 2. Remote tools: the NEXUS MCP server, if a URL is configured.
#    Tools that change your library account wait for you to click Approve in the chat.
NEEDS_APPROVAL = {"alma_renew_user_loan", "alma_cancel_user_request"}

nexus = None
toolsets = []
if mcp_url := os.getenv("NEXUS_MCP_URL"):
    # The SSO login happens while connecting, so allow time to log in (default is 5 seconds).
    nexus = MCPToolset(mcp_url, auth=make_auth(mcp_url), init_timeout=300)
    toolsets.append(nexus.approval_required(lambda ctx, tool, args: tool.name in NEEDS_APPROVAL))

# 3. Local tools: the PubMed MCP server (https://github.com/aeghnnsw/pubmed-mcp), if its
#    folder is configured. It runs as a subprocess of the agent, using the Python in the
#    server's own venv (the server needs MCP SDK 1.x, which differs from this project's).
pubmed = None
if pubmed_dir := os.getenv("PUBMED_MCP_DIR"):
    pubmed_dir = Path(pubmed_dir).expanduser()
    pubmed = MCPToolset(
        PythonStdioTransport(
            script_path=pubmed_dir / "server.py",
            python_cmd=str(pubmed_dir / "venv" / "bin" / "python"),
            cwd=str(pubmed_dir),  # so the server finds its own .env (NCBI key and email)
            # The server's own log output (its MCP 1.x library prints a long, harmless
            # validation warning when this project's newer client first connects).
            log_file=Path(__file__).parent / "pubmed-server.log",
        ),
        id="pubmed",
    )
    toolsets.append(pubmed)


# 4. A plain Python tool: any function the model can choose to call.
#    The docstring becomes the tool description the model sees.
def current_time() -> str:
    """Return the current local date and time."""
    return datetime.now().strftime("%A, %B %d, %Y %I:%M %p")


def today_is() -> str:
    """Added to the instructions so the model always knows today's date."""
    return f"Today is {datetime.now():%A, %B %d, %Y}."


# 5. The agent ties the model, instructions, and tools together.
agent = Agent(
    model,
    instructions=[INSTRUCTIONS, today_is],  # today_is is a function, so it runs fresh on every request
    tools=[current_time],  # local tools
    toolsets=toolsets,  # MCP servers (NEXUS, PubMed)
    output_type=[str, DeferredToolRequests],  # DeferredToolRequests = "paused, waiting for approval"
)
