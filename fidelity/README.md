# Search fidelity traces

Raw data for checking two things:

1. **Query translation:** how the model turns a chat question into `primo_search` arguments.
2. **Presentation:** whether the final answer reports the search results as returned (same items, same order) or reorders, drops, relabels or invents.

Nothing is scored here. `run.py` captures the data; comparing it is up to you.

## Run it

```bash
uv run python -m fidelity.run                 # all 30 questions, 1 run each
uv run python -m fidelity.run --runs 3        # 3 runs each (seed = run number)
uv run python -m fidelity.run --ids Q01,Q29   # selected questions
uv run python -m fidelity.run --no-baselines  # skip the model-free searches
```

Uses the local Ollama model in `OLLAMA_MODEL` (gemma4 by default) and the same instructions and NEXUS tools as the chat agent. Output: `fidelity/results/<timestamp>_<model>.jsonl` (not committed), one line per trial.

## The questions (`questions.json`)

30 chatbot-style questions in 10 categories: `known_item`, `messy_citation`, `partial_or_misspelled`, `edition`, `absent`, `author_only`, `ambiguous_title`, `topic`, `format_or_filter`, `reading_list`.

- `gt_id` links known-item questions to `benchmark/ground_truth.json`, where held/absent is already verified (T01–T10 held, T11–T20 invented).
- `reference_args` is a hand-written, correctly shaped `primo_search` call for the same intent, or `null` when there is no single right search (topics, reading lists, open filters).

## What each line contains

| Field | What it is |
|---|---|
| `trial_id`, `question_id`, `category`, `gt_id`, `question`, `model`, `run`, `seed` | What was asked, to which model |
| `status` | `ok`, `paused_for_approval`, or `error` (with `error_type`, `error`) |
| `started_at`, `finished_at`, `total_s` | Wall-clock time for the whole question |
| `steps` | Every step in order: `user_prompt`, `model_request`, `call_tools`, `end`, each with `duration_s`. `model_request` time is the model thinking and writing; `call_tools` time is the tool calls |
| `model_responses` | Each model response in order: `thinking` (reasoning text, if the model returned any), `text`, and `tool_calls` (tool name and exact arguments) |
| `tool_calls` | Every call that reached the MCP server: `args_sent`, raw `result`, `status` (`ok` / `error` / `cancelled`), `error` text, `duration_s`, timestamps. For `primo_search`, `result_record_ids` lists the result's Primo record ids **in the order returned** |
| `final_answer` | The text the user would see |
| `answer_record_ids` | Primo record ids linked in the answer, **in the order they appear** (from `docid=` in the record links) |
| `searched_record_ids` | All record ids from all `primo_search` results in the trial, in order, de-duplicated |
| `pending_approvals` | Account-changing tool calls waiting for approval, if any |
| `usage` | Model requests and tokens |
| `replays` | Each of the model's `primo_search` calls sent again with the exact same arguments, **no model involved**. Compare with `result_record_ids` to see how much NEXUS varies on an identical request (the noise floor) |
| `reference_search` | The `reference_args` search, no model involved: what a correctly shaped search returns. Compare with the model's searches to see what its rewriting changed |
| `full_messages` | The complete Pydantic AI message history, for anything not pulled out above |

## Comparisons this supports

- **Query translation:** `question` → `tool_calls[].args_sent`, against `reference_args`.
- **Search result vs. reference:** `tool_calls[].result_record_ids` vs. `reference_search.record_ids` (overlap, top-1 match, rank order).
- **Noise floor:** `tool_calls[].result_record_ids` vs. `replays[].record_ids`.
- **Presentation:** `searched_record_ids` vs. `answer_record_ids`: what was shown, in what order, what was dropped, and anything in the answer that no search returned.
- **Label accuracy:** each answer item's wording (held / interlibrary loan) vs. that record's `Holding ID` in the raw `result`.
- **Time:** `steps[].duration_s` and `tool_calls[].duration_s`.

## Limits

- Record ids in the answer come only from record links. If the model names a book without a link, match `final_answer` against result titles instead.
- The raw `result` is the tool result as Pydantic AI receives it from the MCP client, not the low-level protocol messages.
- Reasoning text is only captured if the model returns it. Check `model_responses[].thinking` before relying on it.
