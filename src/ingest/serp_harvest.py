from __future__ import annotations
from typing import Any, Dict, List
from urllib.parse import urlparse

from src.ingest.serp_fetch import google_search

# Domain allow/block lists are optional; fall back to empty sets if file is missing.
try:
    from src.config.domains import ALLOW_DOMAINS, BLOCK_DOMAINS  # optional
except Exception:
    ALLOW_DOMAINS: set[str] = set()
    BLOCK_DOMAINS: set[str] = set()


def _domain_of(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


def _source_score(domain: str, position: int) -> float:
    """
    Lightweight trust/rank scoring used to order SERP items for prompting:
    - allow-list: +1.0
    - block-list: -0.9
    - organic position: better ranks get a small boost
    """
    score = 1.0
    if domain in ALLOW_DOMAINS:
        score += 1.0
    if domain in BLOCK_DOMAINS:
        score -= 0.9
    score += max(0, (10 - min(position, 10))) * 0.03  # pos 1..10 -> +0.27..+0.03
    return score


def harvest_for_queries(queries: List[str], num_per_query: int = 10) -> Dict[str, Any]:
    """
    For each query:
      - collect organic results (title, link, snippet)
      - collect People Also Ask (related_questions)
      - collect knowledge_graph / answer_box when present
    Then:
      - de-dup by URL
      - score and sort by _source_score
    """
    items: List[Dict[str, Any]] = []
    related_questions: List[Dict[str, str]] = []
    seen_links: set[str] = set()

    for q in queries:
        data = google_search(q, num=num_per_query)

        # Organic
        for i, it in enumerate(data.get("organic_results", []) or [], start=1):
            link = (it.get("link") or "").strip()
            if not link or link in seen_links:
                continue
            seen_links.add(link)
            dom = _domain_of(link)
            items.append(
                {
                    "query": q,
                    "position": i,
                    "title": it.get("title"),
                    "link": link,
                    "displayed_link": it.get("displayed_link"),
                    "snippet": it.get("snippet"),
                    "domain": dom,
                    "score": _source_score(dom, i),
                    "type": "organic",
                }
            )

        # People Also Ask
        for rq in data.get("related_questions", []) or []:
            q_text = rq.get("question") or rq.get("title")
            a_text = rq.get("snippet")
            if q_text and a_text:
                related_questions.append({"q": q_text, "a": a_text})

        # Knowledge Graph
        kg = data.get("knowledge_graph")
        if kg:
            src_link = (kg.get("source", {}) or {}).get("link") or ""
            items.append(
                {
                    "query": q,
                    "position": 0,
                    "title": kg.get("title"),
                    "link": src_link,
                    "snippet": kg.get("description"),
                    "domain": _domain_of(src_link),
                    "score": 1.5,
                    "type": "knowledge_graph",
                }
            )

        # Answer Box
        ab = data.get("answer_box")
        if ab:
            ab_link = ab.get("link") or ""
            items.append(
                {
                    "query": q,
                    "position": 0,
                    "title": ab.get("title") or ab.get("type"),
                    "link": ab_link,
                    "snippet": ab.get("answer") or ab.get("snippet"),
                    "domain": _domain_of(ab_link),
                    "score": 1.4,
                    "type": "answer_box",
                }
            )

    # Sort by score desc
    items.sort(key=lambda x: x["score"], reverse=True)
    return {
        "items": items,
        "related_questions": related_questions,
        "stats": {"total_items": len(items), "total_related": len(related_questions)},
    }