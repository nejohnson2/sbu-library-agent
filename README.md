# Nexus Agent

A simple AI agent for Stony Brook University Libraries. It runs **gemma4** on your machine through Ollama and uses the **SBU NEXUS MCP server** (Clarivate) to search the catalog and look up library and account information. It is built with [Pydantic AI](https://ai.pydantic.dev) and comes with a browser chat interface.

## Requirements

- macOS (login tokens are saved in the macOS Keychain)
- [uv](https://docs.astral.sh/uv/) (installs Python 3.13 and the dependencies)
- [Ollama](https://ollama.com) with the model pulled: `ollama pull gemma4`
- A Stony Brook account for the NEXUS login

## Setup

```bash
cp .env.example .env
uv sync
```

Then set `NEXUS_MCP_URL` in `.env` to the NEXUS MCP server URL (ask the library for it).

## Run the chat

```bash
uv run uvicorn app:app --port 7860
```

Open http://localhost:7860. The server runs until you press Ctrl+C.

**First login:** the first message opens a browser tab with the SBU/Clarivate login. Sign in, then go back to the chat. The chat waits up to 5 minutes for you. The token is then saved in your Keychain (under "nexus-agent") and refreshed automatically, so later runs don't ask you to log in.

To log in or check the connection without the chat, run `uv run python login.py`. It prints the NEXUS tools.

## What the agent can do

| Tool | What it does | Approval needed |
|---|---|---|
| `primo_search` | Search the library catalog | |
| `alma_get_libraries`, `alma_get_library`, `alma_get_library_locations` | Library information | |
| `alma_get_opening_hours` | Opening hours | |
| `alma_get_user_loans`, `alma_get_user_requests`, `alma_get_user_fees` | Your loans, requests and fines | |
| `alma_renew_user_loan` | Renew a loan | **Yes** |
| `alma_cancel_user_request` | Cancel a request | **Yes** |
| `current_time` (local) | Current date and time | |

The two tools that change your library account pause and show **Approve / Deny** in the chat before anything is sent. The list is `NEEDS_APPROVAL` in `agent.py`.

## Testing

```bash
uv run python eval.py
```

This asks a fixed set of questions 3 times each. For each answer it prints the tools used, the details passed to them, and the reply. A run is marked `PASS` when the expected tool was used. Read the answers too, because `PASS` does not check that the answer is correct.

To compare models, change `MODEL_NAME` in `.env` (for example `qwen2.5:7b` or `gpt-oss:20b`) and run it again.

## Files

| File | Purpose |
|---|---|
| `agent.py` | The agent: model, instructions, tools, NEXUS connection |
| `auth.py` | NEXUS OAuth login and token storage |
| `app.py` | Web chat interface |
| `login.py` | Log in and list NEXUS tools from the terminal |
| `eval.py` | Test questions |
| `.env` | Settings (not committed; copy from `.env.example`) |

## Settings (`.env`)

| Variable | Default | Meaning |
|---|---|---|
| `MODEL_NAME` | `gemma4` | Ollama model to use |
| `OLLAMA_BASE_URL` | `http://localhost:11434/v1` | Where Ollama is running |
| `NEXUS_MCP_URL` | (blank) | NEXUS MCP server URL. Leave blank to run without it |
| `PYDANTIC_AI_NO_BANNER` | `1` | Hides the Pydantic AI startup banner |

## Notes and workarounds

- **`websockets` dependency:** FastMCP's login callback needs it but does not install it, so it is listed in `pyproject.toml`.
- **Token refresh fix (`auth.py`):** the MCP library only learns Clarivate's token address during a full login. Without the fix, refreshing a saved token sends the request to the wrong address and you have to log in again. Access tokens last 30 minutes.
- **Login timeout (`init_timeout=300` in `agent.py`):** the login happens while connecting to NEXUS, and the default 5-second limit is too short.
- **Today's date** is added to the instructions on every request. Without it, gemma4 guessed what "today" was in questions like "When is the library open today?".
- **Single user, local only:** the login opens a browser on the machine running the server. Sharing this with other people would need a different login setup.
- You may see a warning that a store "is unstable". It comes from the token storage library and can be ignored.
