# Status

_Last updated: 2026-10-23_

## Current state

Working. The agent runs on the library's LiteLLM gateway (`LLM=litellm`, model `ai11-gpt-oss-20b`) and has two MCP servers: SBU NEXUS (catalog and account, OAuth login saved in Keychain) and a local PubMed server (stdio subprocess).

## Completed this session

- Fixed `.env`: the LiteLLM hostname had a typo (`lbrary.` instead of `library.`), which made every chat request fail.
- Added the PubMed MCP server ([aeghnnsw/pubmed-mcp](https://github.com/aeghnnsw/pubmed-mcp), cloned at `~/Projects/pubmed-mcp`) as a second toolset in `agent.py`, configured by `PUBMED_MCP_DIR` in `.env`.
  - Its repo's `setup.sh` installs MCP SDK 2.x, which breaks it; pinned `mcp<2` in that repo's `venv`. The pin is not recorded in that repo, so rerunning its `setup.sh` will break it again.
  - The agent runs it with the PubMed repo's own `venv/bin/python` (stdio), so no separate process is needed. Its stderr goes to `pubmed-server.log` (gitignored).
- Added PubMed rules to the agent instructions (search, then summaries; check holdings with `primo_search`).
- `login.py` now lists tools from both servers; `eval.py` has a PubMed question.
- README and `.env.example` updated.
- Verified end to end: "Find three recent PubMed articles on CRISPR for sickle cell disease, then check whether the library has Nature Medicine" used `search_articles` -> `get_article_summaries` -> `primo_search` and answered correctly.

## Left to do

- Run the full `uv run python eval.py` with the PubMed question across models (only the gateway model was tried).
- Consider `get_article_summaries` returning XML: the model handles it, but a text or JSON return mode in the PubMed server would cut tokens.
- Optionally add an NCBI API key in `~/Projects/pubmed-mcp/.env` to raise the PubMed rate limit.
- Git: none of this is committed yet (user handles git).

## Known issues

- Model quality on vague catalog questions is uneven (e.g. asked about "Melville Library" hours, `ai11-gpt-oss-20b` looped on `alma_get_libraries` and gave up). Not a connection problem.
- `pubmed-server.log` fills with a long but harmless pydantic validation warning each time the agent connects (MCP 1.x server vs FastMCP 4 client `server/discover` probe).
