"""Run the holdings benchmark: every model x every ground-truth title x N seeded runs.

Each trial asks the production agent's question (same instructions and tools as the chat) with a
different local Ollama model, records the tools it called, any tool errors, its VERDICT line,
and whether the record links it cited actually came from a tool result. One JSON line per trial
is appended to results/<model>.jsonl, so an interrupted run resumes where it stopped; trials that
failed for infrastructure reasons (timeout, Ollama/HTTP error) are run again on resume.

Run with: uv run python -m benchmark.run [--models a,b] [--runs 3] [--dev]
"""

import argparse
import asyncio
import json
import os
import re
import subprocess
import time
from contextlib import AsyncExitStack
from datetime import datetime, timezone

from pydantic_ai import Agent, DeferredToolRequests, capture_run_messages
from pydantic_ai.exceptions import ModelAPIError, UnexpectedModelBehavior, UsageLimitExceeded
from pydantic_ai.messages import RetryPromptPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.ollama import OllamaModel
from pydantic_ai.providers.ollama import OllamaProvider
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import UsageLimits
from tqdm import tqdm

from agent import INSTRUCTIONS, current_time, today_is, toolsets
from benchmark.common import DEFAULT_MODELS, GROUND_TRUTH, PROMPT, RESULTS_DIR, is_infra_failure, setup_logging, slug

log = setup_logging("bench", RESULTS_DIR / "run.log")

VERDICT_RE = re.compile(r"VERDICT:\s*(HELD|NOT HELD|UNSURE)", re.IGNORECASE)
DOCID_RE = re.compile(r"docid=([A-Za-z0-9_]+)")
EXPECTED_VERDICT = {"held": "HELD", "absent": "NOT HELD"}


def build_agent(model_name: str) -> Agent:
    """Same instructions, tools and output type as the production agent; only the model differs."""
    provider = OllamaProvider(base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"))
    return Agent(
        OllamaModel(model_name, provider=provider),
        instructions=[INSTRUCTIONS, today_is],
        tools=[current_time],
        toolsets=toolsets,
        output_type=[str, DeferredToolRequests],
    )


def _stringify(content) -> str:
    try:
        return content if isinstance(content, str) else json.dumps(content, default=str)
    except Exception:
        return str(content)


def inspect_messages(messages) -> dict:
    """Pull tool calls, tool errors and the record ids present in tool results out of the run."""
    calls, errors, docids_seen, error_messages = [], 0, set(), []
    for msg in messages:
        for part in msg.parts:
            if isinstance(part, ToolCallPart):
                calls.append({"tool": part.tool_name, "args": part.args_as_dict() if hasattr(part, "args_as_dict") else part.args})
            elif isinstance(part, RetryPromptPart) and part.tool_name:
                errors += 1  # the tool (or its schema validation) rejected the call
                error_messages.append(f"{part.tool_name}: {_stringify(part.content)[:300]}")
            elif isinstance(part, ToolReturnPart):
                text = _stringify(part.content)
                docids_seen.update(DOCID_RE.findall(text))
                if '"error"' in text[:200] or text.lstrip().startswith("Error"):
                    errors += 1
                    error_messages.append(f"{part.tool_name}: {text[:300]}")
    return {"calls": calls, "errors": errors, "docids_seen": docids_seen, "error_messages": error_messages}


def parse_verdict(text: str) -> str:
    found = VERDICT_RE.findall(text or "")
    return found[-1].upper() if found else "UNPARSED"


async def run_trial(agent: Agent, title: dict, run: int, timeout: float) -> dict:
    prompt = PROMPT.format(title=title["title"], author=title["author"])
    rec = {
        "model": agent.model.model_name,
        "title_id": title["id"],
        "title": title["title"],
        "expected": title["expected"],
        "run": run,
        "seed": run,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    t0 = time.perf_counter()
    output = ""
    with capture_run_messages() as messages:  # keeps the messages when the run raises
        try:
            result = await asyncio.wait_for(
                agent.run(prompt, model_settings=ModelSettings(seed=run), usage_limits=UsageLimits(request_limit=12)),
                timeout=timeout,
            )
            rec["status"] = "ok"
            if isinstance(result.output, DeferredToolRequests):
                rec["status"] = "paused"  # asked for approval of an account-changing tool
            else:
                output = result.output
            usage = result.usage() if callable(result.usage) else result.usage  # method in older versions, attribute now
            rec.update(requests=usage.requests, input_tokens=usage.input_tokens, output_tokens=usage.output_tokens)
        except asyncio.TimeoutError:  # must come before OSError: TimeoutError is an OSError
            rec["status"] = "timeout"
        except (ModelAPIError, OSError) as e:  # Ollama/HTTP or network failure, not the model's answer
            rec["status"], rec["error"] = "infra_error", f"{type(e).__name__}: {e}"[:300]
        except UsageLimitExceeded as e:
            rec["status"], rec["error"] = "limit", str(e)[:300]
        except UnexpectedModelBehavior as e:
            # most often: the model's tool call was rejected twice (bad arguments), which ends the run
            rec["status"] = "tool_retries_exceeded" if "exceeded max retries" in str(e) else "error"
            rec["error"] = f"{type(e).__name__}: {e}"[:300]
        except Exception as e:  # keep the sweep going; the failure is data too
            rec["status"], rec["error"] = "error", f"{type(e).__name__}: {e}"[:300]
    info = inspect_messages(messages)
    rec["latency_s"] = round(time.perf_counter() - t0, 2)

    verdict = parse_verdict(output) if rec["status"] == "ok" else "NONE"
    cited = set(DOCID_RE.findall(output))
    rec.update(
        verdict=verdict,
        correct=verdict == EXPECTED_VERDICT[title["expected"]],
        hallucinated=title["expected"] == "absent" and verdict == "HELD",
        tools=[c["tool"] for c in info["calls"]],
        tool_calls=info["calls"],
        n_tool_calls=len(info["calls"]),
        n_tool_errors=info["errors"],
        tool_error_messages=info["error_messages"],
        used_primo=any(c["tool"] == "primo_search" for c in info["calls"]),
        cited_record_ids=sorted(cited),
        fabricated_links=len(cited - info["docids_seen"]),  # linked a record no tool result contained
        answer=output,
    )
    return rec


def _free_model(model_name: str) -> None:
    """Ask Ollama to unload a model so the next one has the memory (best effort)."""
    try:
        subprocess.run(["ollama", "stop", model_name], check=False, capture_output=True, timeout=30)
    except Exception:
        pass


async def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--models", default=",".join(DEFAULT_MODELS), help="comma-separated Ollama model names")
    ap.add_argument("--runs", type=int, default=3, help="runs per title per model (seed = run number)")
    ap.add_argument("--limit", type=int, default=None, help="only the first N titles (dev)")
    ap.add_argument("--timeout", type=float, default=300, help="seconds per trial")
    ap.add_argument("--dev", action="store_true", help="first model only, 2 titles (one held, one absent), 1 run")
    args = ap.parse_args()

    gt = json.loads(GROUND_TRUTH.read_text())
    titles = gt["titles"]
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    runs = args.runs
    if args.dev:
        models = models[:1]
        held = next(t for t in titles if t["expected"] == "held")
        absent = next(t for t in titles if t["expected"] == "absent")
        titles, runs = [held, absent], 1
    elif args.limit:
        titles = titles[: args.limit]
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    log.info("models=%s titles=%d runs=%d timeout=%ss", models, len(titles), runs, args.timeout)

    async with AsyncExitStack() as stack:
        for ts in toolsets:  # connect to NEXUS once for the whole sweep
            await stack.enter_async_context(ts)

        for model_name in models:
            out_path = RESULTS_DIR / f"{slug(model_name)}.jsonl"
            done = set()
            if out_path.exists():
                for line in out_path.read_text().splitlines():
                    if line.strip():
                        r = json.loads(line)
                        if not is_infra_failure(r):  # infrastructure failures are retried
                            done.add((r["title_id"], r["run"]))
            todo = [(t, r) for t in titles for r in range(1, runs + 1) if (t["id"], r) not in done]
            log.info("%s: %d trials to run (%d already done)", model_name, len(todo), len(done))
            if not todo:
                continue
            agent = build_agent(model_name)
            with out_path.open("a") as f:
                for title, run in tqdm(todo, desc=model_name, unit="trial"):
                    rec = await run_trial(agent, title, run, args.timeout)
                    f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
                    f.flush()
                    log.info("%s %s run%d -> %s %s tools=%s errors=%d %.0fs", model_name, title["id"], run,
                             rec["status"], rec["verdict"], rec["tools"], rec["n_tool_errors"], rec["latency_s"])
            _free_model(model_name)
    log.info("done")


if __name__ == "__main__":
    asyncio.run(main())
