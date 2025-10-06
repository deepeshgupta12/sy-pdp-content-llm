# src/ingest/human_examples.py
from __future__ import annotations
from pathlib import Path
from typing import List, Dict, Tuple
import re
import json


def _parse_front_matter(text: str) -> Tuple[dict, str]:
    """Parse optional YAML-like front matter delimited by --- ... ---"""
    if text.startswith("---"):
        m = re.search(r"^---\n(.*?)\n---\n", text, flags=re.DOTALL)
        if m:
            raw = m.group(1)
            body = text[m.end():]
            meta = {}
            try:
                import yaml  # optional dependency
                meta = yaml.safe_load(raw) or {}
            except Exception:
                # naive "key: value" fallback if PyYAML is absent
                for line in raw.splitlines():
                    if ":" in line:
                        k, v = line.split(":", 1)
                        meta[k.strip()] = v.strip()
            return meta, body
    return {}, text


def _word_count(s: str) -> int:
    return len(re.findall(r"\b\w+\b", s))


def load_examples(
    dir_path: str | Path = "data/human_examples",
    max_files: int = 10,
) -> List[Dict[str, str]]:
    """
    Load up to `max_files` .md/.txt examples with optional front-matter.
    Returns list of dicts: {title, body, style_notes (json string), word_count (str)}
    """
    d = Path(dir_path)
    items: List[Dict[str, str]] = []
    if not d.exists():
        return items

    for p in sorted(d.glob("*")):
        if p.suffix.lower() not in {".md", ".txt"}:
            continue
        text = p.read_text("utf-8")
        meta, body = _parse_front_matter(text)
        body = body.strip()
        if not body:
            continue

        item = {
            "title": str(meta.get("title", p.stem)),
            "body": body,
            "style_notes": json.dumps(
                {
                    "voice": meta.get("voice"),
                    "dos": meta.get("dos"),
                    "donts": meta.get("donts"),
                    "sections_order": meta.get("sections_order"),
                },
                ensure_ascii=False,
            ),
            "word_count": str(_word_count(body)),
        }
        items.append(item)
        if len(items) >= max_files:
            break
    return items