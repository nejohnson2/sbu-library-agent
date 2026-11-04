"""Run the question set through the agent and capture everything, for later comparison.

For every question it records, as one JSON line per trial:
- the question and its metadata (category, ground-truth id, reference search)
- every step of the run with wall-clock timing (model requests, tool-call phases)
- every MCP call: the exact arguments sent, the raw result returned, timing, errors
- any reasoning ("thinking") text the model returned
- the final answer, token usage, and the full Pydantic AI message history
- the ordered Primo record ids in each search result and in the final answer
- two model-free searches for comparison:
    replay    = the model's exact primo_search arguments sent again (noise baseline)
    reference = the hand-written search from questions.json (what a correct search returns)

Nothing is scored here; the output is raw data for comparing later.
Local Ollama only (OLLAMA_MODEL in .env, gemma4 by default).

Run with: uv run python -m fidelity.run [--runs 1] [--ids Q01,Q05] [--no-baselines]
"""

import argparse
import asyncio
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic_ai import Agent, DeferredToolRequests, capture_run_messages
from pydantic_ai.messages import ModelMessagesTypeAdapter, ModelResponse, TextPart, ThinkingPart, ToolCallPart
from pydantic_ai.models.ollama import OllamaModel
from pydantic_ai.providers.ollama import OllamaProvider
from pydantic_ai.settings import ModelSettings
from pydantic_ai.toolsets import WrapperToolset

from agent import INSTRUCTIONS, current_time, nexus, today_is, toolsets

HERE = Path(__file__).parent
QUESTIONS = HERE / "questions.json"
RESULTS_DIR = HERE / "results"
DOCID_RE = re.compile(r"docid=([A-Za-z0-9_]+)")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def as_text(content: Any) -> str:
    """Tool results arrive as a string or as parsed JSON; normalize to text for id extraction."""
    if isinstance(content, str):
        return content
    try:
        return json.dumps(content, default=str)
    except Exception:
        return str(content)


def primo_ids(content: Any) -> list[str]:
    """Ordered Primo record ids in a primo_search result (empty if it isn't one)."""
    text = as_text(content)
    try:
        data = json.loads(text)
        return [item.get("Record ID") for item in data.get("items", []) if isinstance(item, dict)]
    except Exception:
        return re.findall(r'"Record ID":\s*"([^"]+)"', text)


def dedupe(seq: list[str]) -> list[str]:
    return list(dict.fromkeys(seq))


class RecordingToolset(WrapperToolset):
    """Records every tool call that reaches the MCP server: exact args, raw result, timing, errors."""

    def __init__(self, wrapped):
        super().__init__(wrapped)
        self.calls: list[dict] = []

    async def call_tool(self, name, tool_args, ctx, tool):
        entry = {"seq": len(self.calls) + 1, "tool": name, "args_sent": tool_args, "started_at": now()}
        self.calls.append(entry)
        t0 = time.perf_counter()
        try:
            result = await super().call_tool(name, tool_args, ctx, tool)
            entry.update(status="ok", result=result)
            if name == "primo_search":
                entry["result_record_ids"] = primo_ids(result)
            return result
        except Exception as e:  # includes ModelRetry for rejected calls; the model sees this and may retry
            entry.update(status="error", error_type=type(e).__name__, error=str(e))
            raise
        except BaseException:  # the run was stopped (e.g. retry limit hit) while this call was in flight
            entry.update(status="cancelled")
            raise
        finally:
            entry["duration_s"] = round(time.perf_counter() - t0, 3)
            entry["finished_at"] = now()


def build_agent(recorder: RecordingToolset) -> Agent:
    """Same model, instructions and tools as the production agent, with tool calls recorded."""
    provider = OllamaProvider(base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"))
    return Agent(
        OllamaModel(os.getenv("OLLAMA_MODEL", "gemma4"), provider=provider),
        instructions=[INSTRUCTIONS, today_is],
        tools=[current_time],
        toolsets=[recorder],
        output_type=[str, DeferredToolRequests],
    )


def describe_node(node) -> str:
    if Agent.is_user_prompt_node(node):
        return "user_prompt"
    if Agent.is_model_request_node(node):
        return "model_request"
    if Agent.is_call_tools_node(node):
        return "call_tools"
    if Agent.is_end_node(node):
        return "end"
    return type(node).__name__


async def run_question(q: dict, run: int, model_name: str) -> dict:
    recorder = RecordingToolset(toolsets[0])
    agent = build_agent(recorder)
    rec: dict[str, Any] = {
        "trial_id": f"{q['id']}-r{run}",
        "question_id": q["id"],
        "category": q["category"],
        "gt_id": q.get("gt_id"),
        "question": q["question"],
        "reference_args": q.get("reference_args"),
        "model": model_name,
        "run": run,
        "seed": run,
        "started_at": now(),
    }
    steps: list[dict] = []
    t_start = time.perf_counter()
    output: Any = None
    with capture_run_messages() as messages:  # keeps the history even if the run raises
        try:
            async with agent.iter(q["question"], model_settings=ModelSettings(seed=run)) as agent_run:
                t_prev = time.perf_counter()
                prev = None
                async for node in agent_run:
                    t_now = time.perf_counter()
                    if prev is not None:  # each node's time = until the next node arrives
                        prev["duration_s"] = round(t_now - t_prev, 3)
                    prev = {"step": len(steps) + 1, "kind": describe_node(node), "started_at": now()}
                    steps.append(prev)
                    t_prev = t_now
                if prev is not None:
                    prev["duration_s"] = round(time.perf_counter() - t_prev, 3)
                result = agent_run.result
            output = result.output
            rec["status"] = "paused_for_approval" if isinstance(output, DeferredToolRequests) else "ok"
            usage = result.usage() if callable(result.usage) else result.usage
            rec["usage"] = {"requests": usage.requests, "input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens}
        except Exception as e:  # keep going; the failure is data too
            rec.update(status="error", error_type=type(e).__name__, error=str(e)[:2000])
    rec["total_s"] = round(time.perf_counter() - t_start, 3)
    rec["finished_at"] = now()
    rec["steps"] = steps

    # What the model said and thought, per response, in order
    responses = []
    for msg in messages:
        if isinstance(msg, ModelResponse):
            responses.append({
                "timestamp": msg.timestamp.isoformat() if msg.timestamp else None,
                "thinking": [p.content for p in msg.parts if isinstance(p, ThinkingPart)],
                "text": [p.content for p in msg.parts if isinstance(p, TextPart)],
                "tool_calls": [{"tool": p.tool_name, "args": p.args, "tool_call_id": p.tool_call_id}
                               for p in msg.parts if isinstance(p, ToolCallPart)],
            })
    rec["model_responses"] = responses
    rec["tool_calls"] = recorder.calls

    answer = output if isinstance(output, str) else ""
    rec["final_answer"] = answer
    if isinstance(output, DeferredToolRequests):
        rec["pending_approvals"] = [{"tool": c.tool_name, "args": c.args} for c in output.approvals]
    rec["answer_record_ids"] = dedupe(DOCID_RE.findall(answer))
    rec["searched_record_ids"] = dedupe([i for c in recorder.calls for i in c.get("result_record_ids", [])])
    rec["full_messages"] = ModelMessagesTypeAdapter.dump_python(list(messages), mode="json")
    return rec


async def baseline_search(args: dict) -> dict:
    """One primo_search call with no model involved."""
    t0 = time.perf_counter()
    try:
        r = await nexus.client.call_tool("primo_search", args, raise_on_error=False)
        text = "".join(getattr(c, "text", "") for c in r.content)
        out = {"args": args, "status": "error" if r.is_error else "ok", "record_ids": [] if r.is_error else primo_ids(text)}
        if r.is_error:
            out["error"] = text[:1000]
        else:
            out["result"] = text
    except Exception as e:
        out = {"args": args, "status": "error", "error": f"{type(e).__name__}: {e}"[:1000], "record_ids": []}
    out["duration_s"] = round(time.perf_counter() - t0, 3)
    return out


async def add_baselines(rec: dict) -> None:
    rec["replays"] = [
        {"seq": c["seq"], **await baseline_search(c["args_sent"])}
        for c in rec["tool_calls"] if c["tool"] == "primo_search"
    ]
    rec["reference_search"] = await baseline_search(rec["reference_args"]) if rec["reference_args"] else None


async def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", type=int, default=1, help="runs per question (seed = run number)")
    ap.add_argument("--ids", default="", help="comma-separated question ids, e.g. Q01,Q05 (default: all)")
    ap.add_argument("--no-baselines", action="store_true", help="skip the model-free replay and reference searches")
    args = ap.parse_args()

    if nexus is None:
        raise SystemExit("Set NEXUS_MCP_URL in .env first.")
    questions = json.loads(QUESTIONS.read_text())["questions"]
    if args.ids:
        wanted = {i.strip() for i in args.ids.split(",")}
        questions = [q for q in questions if q["id"] in wanted]
    model_name = os.getenv("OLLAMA_MODEL", "gemma4")

    RESULTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_path = RESULTS_DIR / f"{stamp}_{re.sub(r'[^a-z0-9]+', '-', model_name.lower())}.jsonl"
    print(f"{len(questions)} questions x {args.runs} runs with {model_name} -> {out_path}")

    async with nexus:  # one NEXUS connection (and at most one login) for the whole run
        with out_path.open("w") as f:
            for q in questions:
                for run in range(1, args.runs + 1):
                    rec = await run_question(q, run, model_name)
                    if not args.no_baselines:
                        await add_baselines(rec)
                    f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
                    f.flush()
                    searches = [c for c in rec["tool_calls"] if c["tool"] == "primo_search"]
                    print(f"{rec['trial_id']:8} {rec['status']:20} {rec['total_s']:6.1f}s  "
                          f"searches={len(searches)} answer_ids={len(rec['answer_record_ids'])}")
    print(f"done -> {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
