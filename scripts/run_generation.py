# scripts/run_generation.py
from __future__ import annotations
import json
import argparse
from pathlib import Path

from src.ingest.load_sy_json import normalize_project_from_file
from src.ingest.providers.sy_datacenter_signature import build_no_repeat_phrases
from src.ingest.query_plan import build_query_plan
from src.ingest.serp_harvest import harvest_for_queries
from src.ingest.human_examples import load_examples
from src.modeling.generator import generate_to_file
from src.export.html_renderer import render_payload_to_html

def main():
    ap = argparse.ArgumentParser(description="Generate PDP JSON (+HTML) for a single project")
    ap.add_argument("--in", dest="in_path", required=True,
                    help="Path to the Square Yards Datacenter JSON for this project")
    ap.add_argument("--out-dir", dest="out_dir", default="out",
                    help="Output directory (default: out)")
    ap.add_argument("--num", dest="num_per_query", type=int, default=8,
                    help="SERP results per query when harvesting (default: 8)")
    ap.add_argument("--cache-only", action="store_true",
                    help="Use existing SERP cache only; do not call SERP")
    ap.add_argument("--site", dest="site_name", default="Square Yards",
                    help="Brand/Site name for the HTML header (default: Square Yards)")
    args = ap.parse_args()

    in_path = Path(args.in_path)
    if not in_path.exists():
        raise SystemExit(f"[ERR] Input JSON not found: {in_path}")

    # Normalize and build dedupe list
    project = normalize_project_from_file(str(in_path))
    no_repeat = build_no_repeat_phrases(project)

    # Decide evidence source (cache vs harvest)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    merged = Path(f"data/serp_cache/{project.project_id}_merged.json")

    if merged.exists():
        data = json.loads(merged.read_text(encoding="utf-8"))
        harvest = data.get("harvest", {})
    else:
        if args.cache_only:
            print("[WARN] Cache-only requested but no cache found; continuing with empty harvest")
            harvest = {}
        else:
            qplan = build_query_plan(project)
            harvest = harvest_for_queries(qplan, num_per_query=args.num_per_query)
            merged.parent.mkdir(parents=True, exist_ok=True)
            merged.write_text(json.dumps({"project": project.model_dump(),
                                          "harvest": harvest}, ensure_ascii=False, indent=2), encoding="utf-8")

    # Human examples (up to 10)
    examples = load_examples("data/human_examples", max_files=10)
    (out_dir / "examples_index.json").write_text(
        json.dumps(examples, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Generate JSON
    json_path = out_dir / f"{project.project_id}_content.json"
    p = generate_to_file(project, harvest, no_repeat, examples, json_path)
    print(f"[OK] Wrote JSON -> {p}")

    # Render HTML alongside
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    html_str = render_payload_to_html(payload, site_name=args.site_name)
    html_path = out_dir / f"{project.project_id}.html"
    html_path.write_text(html_str, encoding="utf-8")
    print(f"[OK] Wrote HTML -> {html_path}")

if __name__ == "__main__":
    main()