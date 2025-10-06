from __future__ import annotations
from pathlib import Path

from .providers.sy_datacenter_signature import (
    load_sy_datacenter_json,
    map_sy_envelope_to_norm,
    build_no_repeat_phrases,
    ProjectNorm,
)

def normalize_project_from_file(path: str | Path) -> ProjectNorm:
    env = load_sy_datacenter_json(path)
    return map_sy_envelope_to_norm(env)

def build_no_repeat_phrases_from_file(path: str | Path):
    p = normalize_project_from_file(path)
    return build_no_repeat_phrases(p)