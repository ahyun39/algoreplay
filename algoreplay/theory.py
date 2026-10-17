"""Theory documents: built-in docs (algoreplay/theory/*.md) plus `theory/*.md` synced from the user's repo.

A repository document with the same name overrides the built-in one.
"""
import re
from pathlib import Path

BUILTIN_DIR = Path(__file__).parent / "theory"


def _all_docs(db):
    docs = {p.stem: p.read_text(encoding="utf-8") for p in sorted(BUILTIN_DIR.glob("*.md"))}
    docs.update({r["name"]: r["content"] for r in db.execute("SELECT name, content FROM theory")})
    return docs


def search_theory(db, topics, limit=3):
    """Exact topic-name matches first, then keyword frequency.
    ponytail: keyword scoring; switch to embeddings when documents outgrow this."""
    docs = _all_docs(db)
    words = {w for t in topics for w in re.split(r"[\s_\-]+", t.lower()) if len(w) > 1}
    scored = []
    for name, content in docs.items():
        score = 100 * (name in topics) + sum(content.lower().count(w) for w in words)
        if score:
            scored.append((-score, name, content))
    return [{"name": n, "content": c} for _, n, c in sorted(scored)[:limit]]


def section(content, heading_keyword):
    """Body of the first `##` section whose heading contains the keyword."""
    m = re.search(rf"^##[^\n]*{heading_keyword}[^\n]*\n(.*?)(?=^##|\Z)", content, re.M | re.S)
    return m.group(1).strip() if m else None
