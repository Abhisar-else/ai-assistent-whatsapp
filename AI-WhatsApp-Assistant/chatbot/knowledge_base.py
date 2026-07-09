"""
Knowledge base loader + retriever.

Source of truth = files in knowledge_base/ (.md and .json). On every
startup we wipe and rebuild the `knowledge_base` SQLite table from those
files, so an admin edits plain files and never touches app code.

Retrieval is a simple keyword-overlap scorer — no vector DB, which is
appropriate given the small, curated content set (PRD explicitly allows
this at this scale).
"""
import json
import logging
import re
from pathlib import Path

from config.settings import settings
from database.db import get_connection

logger = logging.getLogger("knowledge_base")

_STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "do", "does", "did",
    "you", "your", "i", "me", "my", "we", "our", "of", "to", "for", "in",
    "on", "at", "and", "or", "what", "how", "can", "could", "would",
    "about", "with", "it", "this", "that", "please", "hi", "hello",
}


def _tokenize(text: str) -> set:
    words = re.findall(r"[a-zA-Z']+", text.lower())
    return {w for w in words if w not in _STOPWORDS and len(w) > 2}


def _parse_markdown(path: Path):
    """Split a markdown file into (heading, content) sections on '## ' headers."""
    text = path.read_text(encoding="utf-8")
    sections = []
    current_heading = path.stem
    current_lines = []

    for line in text.splitlines():
        if line.startswith("## "):
            if current_lines:
                sections.append((current_heading, "\n".join(current_lines).strip()))
            current_heading = line[3:].strip()
            current_lines = []
        elif line.startswith("# "):
            continue  # top-level doc title, not a topic itself
        else:
            current_lines.append(line)

    if current_lines:
        sections.append((current_heading, "\n".join(current_lines).strip()))

    return [(h, c) for h, c in sections if c]


def _parse_json_faq(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    return [(item["question"], item["answer"]) for item in data if item.get("question") and item.get("answer")]


def load_knowledge_base():
    """Rebuild the knowledge_base table from files. Call on app startup."""
    kb_dir = Path(settings.KNOWLEDGE_BASE_DIR)
    if not kb_dir.exists():
        logger.warning("Knowledge base dir %s does not exist — skipping load.", kb_dir)
        return

    entries = []  # (topic, content, source_file)

    for md_file in sorted(kb_dir.glob("*.md")):
        for topic, content in _parse_markdown(md_file):
            entries.append((topic, content, md_file.name))

    for json_file in sorted(kb_dir.glob("*.json")):
        try:
            for topic, content in _parse_json_faq(json_file):
                entries.append((topic, content, json_file.name))
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            logger.error("Failed to parse KB json file %s: %s", json_file, exc)

    with get_connection() as conn:
        conn.execute("DELETE FROM knowledge_base")
        conn.executemany(
            "INSERT INTO knowledge_base (topic, content, source_file) VALUES (?, ?, ?)",
            entries,
        )

    logger.info("Knowledge base loaded: %d entries from %s", len(entries), kb_dir)


def _token_overlap_score(query_tokens: set, entry_tokens: set) -> float:
    """
    Exact matches score 1, substring matches (e.g. 'web' <-> 'website')
    score 0.5 so an exact match always outranks a partial one — this stops
    incidental substring mentions from outranking the actual topic.
    """
    score = 0.0
    for qt in query_tokens:
        if qt in entry_tokens:
            score += 1.0
            continue
        if len(qt) >= 4 and any(len(et) >= 4 and (qt in et or et in qt) for et in entry_tokens):
            score += 0.5
    return score


def search_knowledge_base(query: str, top_k: int = 3, min_score: float = 1.0):
    """
    Simple keyword-overlap search (exact match weighted higher than
    substring match). Returns up to top_k (topic, content, score) tuples
    with score >= min_score, best first, with topic-title matches boosted.
    """
    query_tokens = _tokenize(query)
    if not query_tokens:
        return []

    with get_connection() as conn:
        rows = conn.execute("SELECT topic, content FROM knowledge_base").fetchall()

    scored = []
    for row in rows:
        topic_tokens = _tokenize(row["topic"])
        content_tokens = _tokenize(row["content"])
        # A hit in the topic/heading itself is a stronger signal than a hit
        # buried in body text, so weight it higher.
        score = (
            _token_overlap_score(query_tokens, topic_tokens) * 2
            + _token_overlap_score(query_tokens, content_tokens)
        )
        if score >= min_score:
            scored.append((row["topic"], row["content"], score))

    scored.sort(key=lambda x: x[2], reverse=True)
    return scored[:top_k]
