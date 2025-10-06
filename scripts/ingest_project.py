from __future__ import annotations
import json
from pathlib import Path
import argparse

from src.ingest.load_sy_json import normalize_project_from_file
from src.ingest.providers.sy_datacenter_signature import build_no_repeat_phrases
from src.ingest.query_plan import build_query_plan
from src.ingest.serp_harvest import harvest_for_queries

def main():
    ap = argparse.ArgumentParser(description="Ingest SY Datacenter JSON and harvest SERP evidence")
    ap.add_argument("--in", dest="in_path", required=True, help="Path to SY Datacenter JSON")
    ap.add_argument("--num", dest="num", type=int, default=10, help="Results per query (default 10)")
    args = ap.parse_args()

    norm = normalize_project_from_file(args.in_path)
    print("[NORM]", norm.model_dump())

    no_repeat = build_no_repeat_phrases(norm)
    print(f"[NO-REPEAT] {no_repeat}")

    qplan = build_query_plan(norm)
    print("[QUERIES]")
    for q in qplan:
        print("  -", q)

    harvest = harvest_for_queries(qplan, num_per_query=args.num)

    out_dir = Path("data/serp_cache")
    out_dir.mkdir(parents=True, exist_ok=True)
    merged_path = out_dir / f"{norm.project_id}_merged.json"
    merged_path.write_text(json.dumps({
        "project": norm.model_dump(),
        "no_repeat": no_repeat,
        "queries": qplan,
        "harvest": harvest
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] Wrote merged SERP corpus -> {merged_path}")

if __name__ == "__main__":
    main()