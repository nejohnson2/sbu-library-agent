"""Ask the agent a fixed set of questions and show which tools it used. Run with: uv run python eval.py"""

import asyncio

from pydantic_ai import DeferredToolRequests
from pydantic_ai.messages import ToolCallPart

from agent import agent

# (question, tool we expect it to use; None = should answer without NEXUS tools)
QUESTIONS = [
    ("Find books about marine biology", "primo_search"),
    ("When is the main library open today?", "alma_get_opening_hours"),
    ("What books do I have checked out?", "alma_get_user_loans"),
    ("Do I owe any library fines?", "alma_get_user_fees"),
    ("Hi, what can you do?", None),
]
RUNS = 3  # the model is a bit random, so ask each question more than once


async def main():
    async with agent:  # connect to NEXUS once for all questions
        for question, expected in QUESTIONS:
            print(f"\n=== {question}   (expected: {expected or 'no NEXUS tool'})")
            for run in range(1, RUNS + 1):
                result = await agent.run(question)
                calls = [p for m in result.all_messages() for p in m.parts if isinstance(p, ToolCallPart)]
                used = [c.tool_name for c in calls]
                ok = expected in used if expected else all(name == "current_time" for name in used)
                print(f"  run {run}: {'PASS ' if ok else 'CHECK'} tools={used or 'none'}")
                for c in calls:
                    print(f"           {c.tool_name}({c.args})")
                if isinstance(result.output, DeferredToolRequests):
                    print("           answer: (paused, waiting for approval)")
                else:
                    print(f"           answer: {result.output[:300]!r}")


asyncio.run(main())
