# Known flaws (pre-registered before the Counterfact run)

_Written 2026-11-02, before running Counterfact on `agent.py`. Not to be edited after the run; score the report against it as is._

Counterfact reads the agent's prompts, tools and code statically. It does not run the agent. So each flaw below carries a prediction: **should find** (visible in `agent.py`/`auth.py`), **might find** (needs the NEXUS tool schemas, which are not in the repo unless `nexus_tools.json` is committed first), or **unlikely** (only visible at runtime). Section C lists flaws that are already fixed: if the report flags one of those, that is a false positive.

Scoring after the run: for each row mark **found / partly / missed**, and add any finding not on this list to section D as a **new true positive** or a **false positive**.

## A. Open flaws (present in the code today)

| # | Flaw | Where | Severity | Prediction |
|---|---|---|---|---|
| A1 | **Approval gate is a blocklist by name.** `NEEDS_APPROVAL` names two tools; every other NEXUS tool runs without asking. The tool list is controlled by Clarivate and loaded at runtime, so a new account-changing tool (e.g. a future `alma_place_request`) would run unguarded. Safer: approve by default, allowlist the known read-only tools. | `agent.py:50,58` | High | Should find |
| A2 | **Write tools accept unverified IDs.** The model can call `alma_cancel_user_request` / `alma_renew_user_loan` with a `request_id`/`loan_id` it invented or took from the wrong item. Nothing checks the ID came from a prior `alma_get_user_requests`/`alma_get_user_loans` result; the approval dialog shows the ID but the human must catch it. | `agent.py:58` | Medium | Should find |
| A3 | **Prompt vs. tool schema mismatch.** The instruction says "using the title and author fields", but the NEXUS schema wants `{"terms": [...]}` objects, not strings. In the benchmark `gemma4:26b` sent a malformed first call on 100% of trials and `gemma4:latest` crashed 40% of trials on it; `ai11-gemma4-12b` on the gateway sent `"title": "marine biology"` and got server errors. | `agent.py:23-24` | High | Might find (needs schemas) |
| A4 | **Prompt contradicts the tool's own description.** Our rule says never say "available"; the `primo_search` description from the server says to use it for "on-site availability". The model gets two conflicting instructions about the same tool. | `agent.py:28-29` vs. server schema | Medium | Might find (needs schemas) |
| A5 | **Tools are invisible to static review.** All NEXUS tools arrive from a remote MCP server behind SSO; the repo contains one `MCPToolset(mcp_url, ...)` line and no schemas. Nothing in the repo can be checked against the real tool contract. `max_retries=2` is the only mitigation. | `agent.py:57` | Medium | Should find (should at least say it cannot see the tools) |
| A6 | **Loose retry can produce a false "held".** "Try once more with just the main title words" can match a different book with similar words and report it as held. The benchmark's absent titles were invented, so this path was not stressed. | `agent.py:25-26` | Medium | Should find |
| A7 | **Unbounded tool loop on long lists.** "Run a separate primo_search for each item" has no cap. A 40-item reading list is 40+ calls against a server with a 25 req/s rate limit, with no instruction to batch or stop. Only Pydantic AI's default request limit bounds it. | `agent.py:23-24` | Low | Should find |
| A8 | **Patron data leaves the machine silently.** With `LLM=litellm`, questions and tool results (loans, fines, requests) go to the remote gateway. Nothing in the UI or code tells the user which mode is active. | `agent.py:40-45` | Medium | Should find |
| A9 | **One identity for all users.** The NEXUS token lives in one Keychain entry; the web UI has no login. Anyone who reaches the chat acts as the token owner. Fine on a laptop, dangerous if the server is ever exposed. | `auth.py:15-20`, `app.py` | High (if deployed) | Should find |
| A10 | **Silent fallback on misconfiguration.** Any `LLM` value other than `litellm` (typo, `LiteLLM`, `remote`) silently uses local Ollama. | `agent.py:40` | Low | Should find |
| A11 | **Fixed OAuth callback port.** Port 8765 is hard-coded; if it is busy (seen once when two processes ran), login fails with "address already in use". | `auth.py:19` | Low | Should find |
| A12 | **Startup degrades without telling the UI.** If the NEXUS discovery lookup fails, `make_auth` prints a warning to the terminal and continues; the chat user sees only failing tool calls later. | `auth.py:21-29` | Low | Should find |

## B. Runtime flaws (seen in the benchmark; not visible in the code)

| # | Flaw | Evidence | Prediction |
|---|---|---|---|
| B1 | Small models read correct records and still answer NOT HELD. | `qwen2.5:7b`: 8/30 held trials | Unlikely |
| B2 | Models invent parameters (`location`, `keyword`) that the schema does not have. | `gpt-oss:20b` rejected calls | Unlikely |
| B3 | Ollama itself fails to parse the model's tool-call JSON (HTTP 500). | 2 `gpt-oss:20b` trials | Unlikely |
| B4 | `Available: null` in results does not mean on the shelf; Primo showed a null-marked book as checked out. | manual check 2026-11-02 | Unlikely |
| B5 | Small models fabricate a Primo record as JSON and conclude HELD. | `llama3.2`: 4/30 absent trials | Unlikely (the prompt cannot prevent it; only a stronger model or a link-check can) |
| B6 | Shelf status, location and call number are not in `primo_search` at all; they need a separate (public PNX) call that the agent does not have. | manual check 2026-11-02 | Unlikely |
| B7 | SSO refresh token expires after several days idle; the browser login reopens mid-use. | observed 10/20, 11/02 | Unlikely |

## C. Fixed flaws (negative controls: flagging these is a false positive)

| # | Flaw | Fixed by |
|---|---|---|
| C1 | Model guessed what "today" was (said Oct 19 on Oct 15). | `today_is` in instructions |
| C2 | Model asked "would you like me to search?" before read-only searches. | rule at `agent.py:22` |
| C3 | Model ran one combined search for a reading list. | rule at `agent.py:23-24` |
| C4 | Model said "very likely available" without searching. | rule at `agent.py:21,27` |
| C5 | Model linked other SUNY libraries' records as Stony Brook copies. | rule at `agent.py:30-32` |
| C6 | Model claimed availability / on-shelf status the data does not carry. | rule at `agent.py:28-29,33-35` |
| C7 | 5-second MCP init timeout killed the SSO login. | `init_timeout=300` |
| C8 | Token refresh went to the wrong URL in a new process (MCP library bug). | `fetch_oauth_metadata` in `auth.py` |
| C9 | Agent crashed or hung at startup when NEXUS was unreachable. | try/except + 10 s timeouts in `auth.py` |
| C10 | One tool retry; a single malformed call ended the whole request. | `max_retries=2` |
| C11 | Missing `websockets` dependency crashed the OAuth callback server. | `pyproject.toml` |

## D. Findings not on this list (filled in after the run)

| Finding (quote the report) | New true positive / False positive | Notes |
|---|---|---|
| F-1 (medium) "Patrons' hold cancellations can fail quietly or be logged with the wrong reason." `nexus_tools.json:462` | **New true positive** | `alma_cancel_user_request`: description says `reason` "is required, not optional" and must be an Alma code; schema marks it optional, default null. Clarivate's contradiction; the agent can send a cancel with no reason. Suggested fix (make the reason mandatory in our instructions) is local and sensible. |
| F-2 (medium) "Patrons asking which loans they can renew can get failed lookups or guesses." `nexus_tools.json:388` | **New true positive** | `alma_get_user_loans`: description documents `expand: "renewable"`; schema has only `loan_status`. Not fixable on our side; report to Clarivate. |
| F-3 (medium) "Patrons asking about library hours on a future date can get errors or this week's hours." `nexus_tools.json:326` | **New true positive** | `alma_get_opening_hours`: description documents `from_date`/`to_date` and calls `scope` required; schema has only an optional `scope`. Not fixable on our side; report to Clarivate. |

## Result (run of 2026-11-02, CLI 0.2.9, inputs: `agent.py`, `auth.py`, `app.py`, `nexus_tools.json`, `pyproject.toml`)

| Measure | Score |
|---|---|
| Section A open flaws found | **0 of 12** (A1 blocklist, A3 prompt-vs-schema, A9 shared identity all missed) |
| Section B runtime flaws found | 0 of 7 (as predicted) |
| Section C fixed flaws wrongly flagged (false positives) | **0 of 11** |
| Findings not on the list | **3, all true positives**, all description-vs-schema contradictions inside Clarivate's tool definitions |
| Findings about our own code or prompt | 0 |

Reading: the tool found nothing wrong in `agent.py` or `auth.py`, including the high-severity design flaws (A1, A9) and the prompt/schema mismatch (A3) that caused the worst benchmark failures. Everything it found came from `nexus_tools.json`, and all of it was real and new to us: it read the tool descriptions against the tool schemas and caught three contradictions we had never checked for. Zero false positives. The experiment-2 question ("can it see the tools?") is answered: yes, when given the schemas, and that is where all its value came from.
