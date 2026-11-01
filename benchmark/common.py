"""Shared paths, defaults and helpers for the holdings benchmark."""

import logging
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BENCH_DIR = ROOT / "benchmark"
GROUND_TRUTH = BENCH_DIR / "ground_truth.json"
RESULTS_DIR = BENCH_DIR / "results"
FIGURES_DIR = BENCH_DIR / "figures"

# Local Ollama models to compare (all open-weight). Override with --models or MODELS= in the Makefile.
DEFAULT_MODELS = [
    "gemma4:latest",
    "gemma4:26b",
    "gpt-oss:20b",
    "qwen3:32b",
    "qwen2.5:7b",
    "llama3.1:latest",
    "llama3.2:latest",
]

# The question asked for every title. The VERDICT line makes the answer machine-readable
# without an LLM judge; a missing line is itself recorded as a failure mode ("UNPARSED").
PROMPT = (
    'Does Stony Brook University Libraries have the book "{title}" by {author}? '
    'End your answer with exactly one line: "VERDICT: HELD", "VERDICT: NOT HELD", or "VERDICT: UNSURE".'
)


def slug(model: str) -> str:
    """'gpt-oss:20b' -> 'gpt-oss-20b' (safe for file names)."""
    return re.sub(r"[^a-z0-9]+", "-", model.lower()).strip("-")


def setup_logging(name: str, log_file: Path | None = None) -> logging.Logger:
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s", "%H:%M:%S")
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file))
    for h in handlers:
        h.setFormatter(fmt)
    logging.basicConfig(level=logging.INFO, handlers=handlers, force=True)
    # the MCP/HTTP libraries are chatty at INFO
    for noisy in ("httpx", "httpx2", "mcp", "fastmcp", "pydantic_ai", "key_value"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    return logging.getLogger(name)
