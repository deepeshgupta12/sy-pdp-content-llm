import json
import hashlib
from pathlib import Path
from typing import Any

from serpapi import GoogleSearch
from src.config import AppConfig

CACHE_DIR = Path("data/serp_cache")


def _cache_key(q: str, hl: str, gl: str, domain: str) -> Path:
    key = hashlib.sha256(f"{q}|{hl}|{gl}|{domain}".encode("utf-8")).hexdigest()
    return CACHE_DIR / f"{key}.json"


def google_search(q: str, num: int = 10) -> dict[str, Any]:
    cfg = AppConfig()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    ck = _cache_key(q, cfg.serp_hl, cfg.serp_gl, cfg.serp_google_domain)
    if ck.exists():
        return json.loads(ck.read_text("utf-8"))

    params = {
        "q": q,
        "engine": "google",
        "hl": cfg.serp_hl,
        "gl": cfg.serp_gl,
        "google_domain": cfg.serp_google_domain,
        "num": num,
        "api_key": cfg.serp_api_key,
    }
    result = GoogleSearch(params).get_dict()
    ck.write_text(json.dumps(result), encoding="utf-8")
    return result