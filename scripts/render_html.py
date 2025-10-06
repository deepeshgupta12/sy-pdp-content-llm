# scripts/render_html.py
from __future__ import annotations
import json
from pathlib import Path
import argparse

from src.export.html_renderer import render_payload_to_html

def main():
    ap = argparse.ArgumentParser(description="Render PDP content JSON to HTML")
    ap.add_argument("--in", dest="in_path", required=True, help="Path to <project_id>_content.json")
    ap.add_argument("--out", dest="out_path", required=False, help="Output HTML path (default: alongside JSON)")
    ap.add_argument("--site", dest="site_name", required=False, default="Square Yards", help="Site/brand name for header")
    args = ap.parse_args()

    in_path = Path(args.in_path)
    if not in_path.exists():
        raise SystemExit(f"[ERR] Input file not found: {in_path}")

    payload = json.loads(in_path.read_text(encoding="utf-8"))
    html_str = render_payload_to_html(payload, site_name=args.site_name)

    if args.out_path:
        out_path = Path(args.out_path)
    else:
        out_dir = in_path.parent
        stem = in_path.stem.replace("_content", "")
        out_path = out_dir / f"{stem}.html"

    out_path.write_text(html_str, encoding="utf-8")
    print(f"[OK] Wrote HTML -> {out_path}")

if __name__ == "__main__":
    main()