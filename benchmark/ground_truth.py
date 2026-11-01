"""Build the ground-truth title list by querying NEXUS directly (no model involved).

Each candidate is searched with primo_search by title and author. A "held" title must return at
least one book record whose title matches; an "absent" title must return nothing. The first
N_HELD and N_ABSENT candidates that pass are written to ground_truth.json.

Run with: uv run python -m benchmark.ground_truth
"""

import asyncio
import json
import re
from datetime import datetime, timezone

from agent import nexus
from benchmark.common import GROUND_TRUTH, setup_logging

log = setup_logging("ground_truth")

N_HELD = 10
N_ABSENT = 10

# Well-known books likely to be in a university library. Verified below; extras are spares.
HELD_CANDIDATES = [
    ("Pattern Recognition and Machine Learning", "Christopher Bishop"),
    ("The Structure of Scientific Revolutions", "Thomas Kuhn"),
    ("Deep Learning", "Ian Goodfellow"),
    ("Artificial Intelligence: A Modern Approach", "Stuart Russell"),
    ("The Elements of Statistical Learning", "Trevor Hastie"),
    ("Silent Spring", "Rachel Carson"),
    ("On the Origin of Species", "Charles Darwin"),
    ("Beloved", "Toni Morrison"),
    ("The Double Helix", "James Watson"),
    ("Thinking, Fast and Slow", "Daniel Kahneman"),
    ("Causality", "Judea Pearl"),
    ("Guns, Germs, and Steel", "Jared Diamond"),
    ("The Selfish Gene", "Richard Dawkins"),
    ("Introduction to Algorithms", "Thomas Cormen"),
    ("A Brief History of Time", "Stephen Hawking"),
    ("Gödel, Escher, Bach", "Douglas Hofstadter"),
]

# Invented titles and authors. Primo indexes an enormous aggregated collection, so a real but
# obscure book could still surface; made-up books are the only safe negatives.
ABSENT_CANDIDATES = [
    ("The Lighthouse at Mariner's Reach", "Elena Thorvald"),
    ("Quantum Gardening for Beginners", "Harold Pembrook"),
    ("A Field Guide to the Moths of Stony Brook Harbor", "Margaret Ashcombe"),
    ("Cartography of Forgotten Rivers", "Tobias Wrenfield"),
    ("The Tidewriter of Ashgrove", "Corinne Valdane"),
    ("Statistical Mechanics of Beekeeping", "Rufus Oyelaran"),
    ("Letters from the Salt Observatory", "Priya Nandakumar-Hale"),
    ("The Nine Bridges of Kessling", "Anselm Durward"),
    ("Migratory Patterns of the Blue Lantern Crab", "Felicity Okonkwo-Marsh"),
    ("An Introduction to Lunar Agronomy", "Desmond Caldwell-Reyes"),
    ("The Weaver's Almanac of 1847", "Hester Pollingbrook"),
    ("Songs of the Hollow Pines", "Marguerite Ellsworth"),
    ("Thermodynamics of Small Islands", "Bartholomew Quince"),
    ("The Glassblower's Atlas", "Ottoline Marchetti-Vance"),
]


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", s.lower())


def _title_matches(wanted: str, got: str) -> bool:
    """The record title must contain the first three words of the wanted title (or all, if fewer)."""
    words = [w for w in _norm(wanted).split() if w not in {"the", "a", "an", "of", "and"}][:3]
    g = _norm(got)
    return all(w in g for w in words)


async def search(title: str, author: str) -> dict:
    res = await nexus.client.call_tool(
        "primo_search",
        {
            "title": {"terms": [title]},
            "author": {"terms": [author.split()[-1]]},  # surname only: Primo author matching is loose
            "join_across_fields": "AND",
            "resources_types": ["books"],
        },
    )
    return res.structured_content or res.data or {}


def _record(item: dict) -> dict:
    return {
        "record_id": item.get("Record ID"),
        "title": (item.get("Title") or "").strip(),
        "is_physical": item.get("Is physical"),
        "is_electronic": item.get("Is electronic"),
        "link": item.get("Record full view"),
    }


async def main():
    if nexus is None:
        raise SystemExit("Set NEXUS_MCP_URL in .env first.")
    held, absent, rejected = [], [], []
    async with nexus:
        for title, author in HELD_CANDIDATES:
            if len(held) >= N_HELD:
                break
            data = await search(title, author)
            items = [i for i in (data.get("items") or []) if isinstance(i, dict)]
            matching = [_record(i) for i in items if _title_matches(title, i.get("Title") or "")]
            if matching:
                held.append({"title": title, "author": author, "expected": "held",
                             "nexus_total": data.get("total"), "records": matching})
                log.info("HELD   %-45s %d matching record(s)", title, len(matching))
            else:
                rejected.append((title, "no matching record", data.get("total")))
                log.warning("REJECT %-45s total=%s, no title match", title, data.get("total"))

        for title, author in ABSENT_CANDIDATES:
            if len(absent) >= N_ABSENT:
                break
            data = await search(title, author)
            total = data.get("total") or 0
            if total == 0 and not data.get("items"):
                absent.append({"title": title, "author": author, "expected": "absent",
                               "nexus_total": 0, "records": []})
                log.info("ABSENT %-45s 0 results", title)
            else:
                rejected.append((title, "unexpected results", total))
                log.warning("REJECT %-45s returned %s result(s)", title, total)

    if len(held) < N_HELD or len(absent) < N_ABSENT:
        log.error("Only %d held and %d absent titles passed; add candidates.", len(held), len(absent))

    titles = held + absent
    for i, t in enumerate(titles, 1):
        t["id"] = f"T{i:02d}"
    out = {
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "method": "primo_search by title + author surname, resources_types=['books']; "
                  "held = >=1 record whose title matches; absent = zero results",
        "n_held": len(held),
        "n_absent": len(absent),
        "rejected": [{"title": t, "reason": r, "total": n} for t, r, n in rejected],
        "titles": titles,
    }
    GROUND_TRUTH.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    log.info("Wrote %s (%d held, %d absent, %d rejected)", GROUND_TRUTH, len(held), len(absent), len(rejected))


if __name__ == "__main__":
    asyncio.run(main())
