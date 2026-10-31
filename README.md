# Stony Brook University Libraries AI Agent

A simple AI agent for Stony Brook University Libraries. It uses the **SBU NEXUS MCP server** (Clarivate) to search the catalog and look up library and account information, and optionally a local **PubMed MCP server** to search biomedical journal articles. The model runs either on your own machine through **Ollama** (gemma4 by default) or on the library's **LiteLLM gateway**. It is built with [Pydantic AI](https://ai.pydantic.dev) and comes with a browser chat interface.

## Requirements

- macOS (login tokens are saved in the macOS Keychain)
- [uv](https://docs.astral.sh/uv/) (installs Python 3.13 and the dependencies)
- A model, either:
  - **local:** [Ollama](https://ollama.com) with the model pulled: `ollama pull gemma4`
  - **remote:** the LiteLLM gateway address and an API key (ask library IT)
- A Stony Brook account for the NEXUS login
- Optional, for PubMed: the [pubmed-mcp](https://github.com/aeghnnsw/pubmed-mcp) repo cloned and set up (see below)

## Setup

```bash
cp .env.example .env
uv sync
```

Then edit `.env`:
- set `NEXUS_MCP_URL` to the NEXUS MCP server URL (ask the library for it)
- to use the gateway, fill in `LITELLM_BASE_URL`, `LITELLM_API_KEY` and `LITELLM_MODEL`, and set `LLM=litellm`
- to add PubMed, set `PUBMED_MCP_DIR` to the folder of the pubmed-mcp repo (see "PubMed server" below)

## Choosing the model

`LLM` in `.env` picks the connection:

| `LLM=` | Model | Where it runs |
|---|---|---|
| `ollama` (default) | `OLLAMA_MODEL`, e.g. `gemma4` | This machine |
| `litellm` | `LITELLM_MODEL`, e.g. `ai11-gpt-oss-20b` | The library's LiteLLM gateway |

Restart the chat server after changing it. To try the other connection once without editing `.env`, put it in front of the command, e.g. `LLM=litellm uv run python eval.py`.

Models that passed the tests in `eval.py`: local `gemma4` and `gpt-oss:20b`, and `ai11-gpt-oss-20b` on the gateway. Models that did not: `ai11-gemma4-12b` and `llama3.1` (see the notes below).

**Privacy:** with `ollama`, your questions and the tool results (including your loans and fines) stay on this machine. With `litellm`, they are sent to the library's gateway.

## Run the chat

```bash
uv run uvicorn app:app --port 7860
```

Open http://localhost:7860. The server runs until you press Ctrl+C.

**First login:** the first message opens a browser tab with the SBU/Clarivate login. Sign in, then go back to the chat. The chat waits up to 5 minutes for you. The token is then saved in your Keychain (under "nexus-agent") and refreshed automatically, so later runs don't ask you to log in until it has gone unused for several days.

To log in or check the connections without the chat, run `uv run python login.py`. It prints the NEXUS and PubMed tools.

## What the agent can do

| Tool | What it does | Approval needed |
|---|---|---|
| `primo_search` | Search the library catalog | |
| `alma_get_libraries`, `alma_get_library`, `alma_get_library_locations` | Library information | |
| `alma_get_opening_hours` | Opening hours | |
| `alma_get_user_loans`, `alma_get_user_requests`, `alma_get_user_fees` | Your loans, requests and fines | |
| `alma_renew_user_loan` | Renew a loan | **Yes** |
| `alma_cancel_user_request` | Cancel a request | **Yes** |
| `search_articles` (PubMed) | Search PubMed, returns PubMed IDs | |
| `get_article_summaries` (PubMed) | Title, authors, journal and date for PubMed IDs | |
| `download_article`, `download_articles_batch` (PubMed) | Abstract or full record for PubMed IDs | |
| `current_time` (local) | Current date and time | |

The two tools that change your library account pause and show **Approve / Deny** in the chat before anything is sent. The list is `NEEDS_APPROVAL` in `agent.py`.

The PubMed tools are only present when `PUBMED_MCP_DIR` is set. The instructions tell the model to use PubMed for research-article questions, and to check the library's holdings with `primo_search` when asked whether an article is available here. Example: *"Find three recent PubMed articles on CRISPR in sickle cell disease and tell me if the library has the journals."*

## PubMed server

The PubMed tools come from a separate open-source MCP server, [aeghnnsw/pubmed-mcp](https://github.com/aeghnnsw/pubmed-mcp), which talks to NCBI's E-utilities. The agent starts it as a subprocess (stdio transport) using the Python in that repo's own `venv`, so nothing else needs to be running. To set it up:

```bash
cd ~/Projects
git clone https://github.com/aeghnnsw/pubmed-mcp.git
cd pubmed-mcp
./setup.sh
venv/bin/pip install "mcp[cli]<2"   # the repo needs MCP SDK 1.x; setup.sh installs 2.x, which breaks it
```

Then set `PUBMED_MCP_DIR=/path/to/pubmed-mcp` in this project's `.env`. Optionally copy that repo's `.env.example` to `.env` and add an NCBI API key and email, which raises NCBI's rate limit from 3 to 10 requests per second.

## Testing

```bash
uv run python eval.py
```

This asks a fixed set of questions 3 times each. For each answer it prints the tools used, the details passed to them, and the reply. A run is marked `PASS` when the expected tool was used. Read the answers too, because `PASS` does not check that the answer is correct.

To compare models, change `OLLAMA_MODEL` (for example `qwen2.5:7b` or `gpt-oss:20b`) or switch `LLM` in `.env`, and run it again.

## Files

| File | Purpose |
|---|---|
| `agent.py` | The agent: model connection, instructions, tools, NEXUS and PubMed connections |
| `auth.py` | NEXUS OAuth login and token storage |
| `app.py` | Web chat interface |
| `login.py` | Log in and list the NEXUS and PubMed tools from the terminal |
| `eval.py` | Test questions |
| `.env` | Settings (not committed; copy from `.env.example`) |

## Settings (`.env`)

| Variable | Default | Meaning |
|---|---|---|
| `LLM` | `ollama` | Which model connection to use: `ollama` (local) or `litellm` (remote gateway) |
| `OLLAMA_BASE_URL` | `http://localhost:11434/v1` | Where the local Ollama is running |
| `OLLAMA_MODEL` | `gemma4` | Local Ollama model to use |
| `LITELLM_BASE_URL` | (blank) | Remote LiteLLM gateway address, ending in `/v1` |
| `LITELLM_API_KEY` | (blank) | API key for the LiteLLM gateway |
| `LITELLM_MODEL` | (blank) | Model name on the gateway, e.g. `ai11-gpt-oss-20b` |
| `NEXUS_MCP_URL` | (blank) | NEXUS MCP server URL. Leave blank to run without it |
| `PUBMED_MCP_DIR` | (blank) | Folder of the pubmed-mcp repo. Leave blank to run without PubMed |
| `PYDANTIC_AI_NO_BANNER` | `1` | Hides the Pydantic AI startup banner |

## Notes and workarounds

- **`websockets` dependency:** FastMCP's login callback needs it but does not install it, so it is listed in `pyproject.toml`.
- **Token refresh fix (`auth.py`):** the MCP library only learns Clarivate's token address during a full login. Without the fix, refreshing a saved token sends the request to the wrong address and you have to log in again. Access tokens last 30 minutes.
- **Login timeout (`init_timeout=300` in `agent.py`):** the login happens while connecting to NEXUS, and the default 5-second limit is too short.
- **Today's date** is added to the instructions on every request. Without it, gemma4 guessed what "today" was in questions like "When is the library open today?".
- **Logging in again after a few days:** access tokens refresh automatically, but after several days without use the SSO refresh token expires and the browser login opens again.
- **Models and tools:** the agent needs a model that is good at tool calling. On the LiteLLM gateway, `ai11-gpt-oss-20b` passed the tests, but `ai11-gemma4-12b` sent search details in the wrong format and NEXUS returned errors. `llama3.1` picked tools but passed bad details and sometimes printed tool calls as text. Local `gemma4` passed the same tests.
- **One model class for both connections:** `agent.py` uses Pydantic AI's Ollama model class for the gateway too. LiteLLM speaks the same OpenAI-style API, and this was tested with `ai11-gpt-oss-20b`.
- **PubMed server and MCP SDK versions:** this project uses FastMCP 4 / MCP SDK 2, but pubmed-mcp is written for SDK 1.x. Running it in its own `venv` with its own Python avoids the conflict, which is why `agent.py` passes an explicit interpreter to the stdio transport. The PubMed server's own messages go to `pubmed-server.log` in this folder (not committed); it contains a long but harmless validation warning that its older MCP library prints when this project's newer client connects.
- **Single user, local only:** the login opens a browser on the machine running the server. Sharing this with other people would need a different login setup.
- You may see a warning that a store "is unstable". It comes from the token storage library and can be ignored.
