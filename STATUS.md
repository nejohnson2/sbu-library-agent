# STATUS

_Last updated: 2026-11-02_

## Current state

The agent (Pydantic AI + NEXUS MCP) works end to end with both the LiteLLM gateway model and local Ollama models. The holdings-trust benchmark is **complete**: 7 models x 20 titles x 3 seeded runs = 420 trials. Results, figures and findings are written up in README.md under "Benchmark".

## Completed this session

- Added the local PubMed MCP server (`PUBMED_MCP_DIR`) to the agent; PubMed tools documented in README; `eval.py` and `login.py` cover it.
- Built `benchmark/` (ground truth, runner, analysis, plots) with a Makefile (`ground-truth`, `bench`, `bench-dev`, `analyze`, `plot`, `clean-results`).
- Ran the full sweep. Headline: zero hallucinated holdings for 5 of 7 models; `llama3.2` hallucinated 13% of the time and once fabricated a Primo record as JSON. `qwen3:32b`, `gemma4:26b` and `gpt-oss:20b` are all 93%+ accurate; `gpt-oss:20b` is the speed/accuracy sweet spot (14 s). `gemma4:26b` malformed its first tool call on 100% of trials and recovered on 98%. `qwen2.5:7b` received correct catalog records and still said NOT HELD on 8/30 held trials.
- Figures: `benchmark/figures/holdings_benchmark.{png,svg}`, `benchmark/figures/latency.{png,svg}`. Table: `benchmark/results/summary.md` (results dir is gitignored; figures are not).

## Completed 2026-11-02 (code review fixes)

- PubMed MCP server removed from the agent, eval, login, `.env.example` and README (it was connected during the 2026-10-31 sweep; README notes this).
- `auth.py`: OAuth discovery has a 10 s timeout and no longer crashes startup when NEXUS is unreachable.
- NEXUS tools get `max_retries=2`; `eval.py` reports a failed question as FAIL and keeps going.
- Benchmark: timeouts and Ollama/HTTP errors are `infra_error`, rerun on resume and excluded from the rates (new column in `summary.md`); fabricated-link check matches all Primo record ids, not only `alma…`.
- Cleanup: package renamed `sbu-library-agent`, `.DS_Store` ignored.
- The README results table predates these changes; re-run `make analyze` (results are not on this machine) or a new sweep to refresh it.

## Known issues / notes

- The sweep stalled once overnight when the laptop lid was closed on battery; `caffeinate` cannot prevent clamshell sleep on battery. Keep the machine on AC with the lid open for long runs. The per-trial timeout uses a monotonic clock and does not fire during sleep.
- The original `gpt-oss:20b` Ollama blob (13 months old) failed with "unsupported tensor ... size overflows"; `ollama pull gpt-oss:20b` fixed it. Two gpt-oss trials still died on Ollama-side tool-call JSON parse errors (HTTP 500).
- NEXUS OAuth refresh token expires after a few days; `uv run python login.py` re-authenticates in the browser.
- Nothing is committed yet (user handles git). Changed/new: `.gitignore`, `README.md`, `STATUS.md`, `pyproject.toml`, `uv.lock`, `Makefile`, `benchmark/` (incl. `ground_truth.json` and `figures/`).

## Next steps

- Write the LinkedIn post from the README findings (figure: `benchmark/figures/holdings_benchmark.png`).
- Optional follow-ups: more titles / runs to tighten the Wilson intervals; test whether a schema example in the instructions fixes gemma4's first-call failures; add the LiteLLM gateway model as a comparison row.
