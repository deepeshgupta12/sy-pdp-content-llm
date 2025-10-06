# src/export/html_renderer.py
from __future__ import annotations

import json
import html
import re
from typing import Any, Dict, List, Tuple

# Use python-markdown if available (best: tables/lists), else safe fallback.
try:
    import markdown as _md
    _HAS_MD = True
except Exception:
    _HAS_MD = False

_SHORT_ANSWER_PREFIX = re.compile(r"(?i)\bshort\s*answer\s*\([^)]*\)\s*:\s*")

def _strip_short_answer_prefix(text: str) -> str:
    return _SHORT_ANSWER_PREFIX.sub("", text or "")

def _md_to_html(text: str) -> str:
    if not text:
        return ""
    text = _strip_short_answer_prefix(text)
    if _HAS_MD:
        return _md.markdown(text, extensions=["extra", "sane_lists", "toc"], output_format="html")
    # ---- Minimal, conservative fallback ----
    s = html.escape(text)

    # Headings
    s = re.sub(r"(?m)^######\s+(.*)$", r"<h6>\1</h6>", s)
    s = re.sub(r"(?m)^#####\s+(.*)$",  r"<h5>\1</h5>", s)
    s = re.sub(r"(?m)^####\s+(.*)$",   r"<h4>\1</h4>", s)
    s = re.sub(r"(?m)^###\s+(.*)$",    r"<h3>\1</h3>", s)
    s = re.sub(r"(?m)^##\s+(.*)$",     r"<h2>\1</h2>", s)
    s = re.sub(r"(?m)^#\s+(.*)$",      r"<h1>\1</h1>", s)

    # Bold/italic
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", s)

    # Links
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<a href="\2" rel="nofollow noopener" target="_blank">\1</a>', s)

    # Bullet list blocks: lines starting with -, +, or * -> <ul>
    def _ul_block(m):
        items = []
        for line in m.group(0).strip().splitlines():
            line = line.strip()
            if not line:
                continue
            # strip marker (-|*|+)
            items.append(f"<li>{line[1:].strip()}</li>")
        return "<ul>\n" + "\n".join(items) + "\n</ul>\n"

    s = re.sub(r"(?ms)^(?:[\-\*\+]\s+.+\n)+", _ul_block, s)

    # Paragraphs by blank line
    parts = [p for p in re.split(r"\n\s*\n", s) if p.strip()]
    return "".join([p if p.strip().startswith("<") else f"<p>{p}</p>" for p in parts])

_SECTION_TITLES = {
    "who_is_it_for": "Who is it for?",
    "location_connectivity": "Location & Connectivity",
    "unit_mix_floorplans": "Unit Mix & Floor Plans",
    "amenities_lifestyle": "Amenities & Lifestyle",
    "pricing_payment_notes": "Pricing & Payment Notes",
    "construction_status_rera": "Construction Status & RERA",
    "developer_profile_eeat": "Developer Profile (E-E-A-T)",
    "nearby_alternatives": "Nearby Alternatives",
    "faqs": "FAQs",
}

def _pluck_md(sec: Any, extra_table_key: str | None = None) -> str:
    if not sec:
        return ""
    if isinstance(sec, str):
        return sec.strip()
    if isinstance(sec, list):
        return "\n\n".join([_pluck_md(x) for x in sec if x]).strip()
    if isinstance(sec, dict):
        parts: List[str] = []
        for key in ("lead", "content", "body", "markdown", "text"):
            val = sec.get(key)
            if isinstance(val, str):
                v = val.strip()
                if v:
                    parts.append(v)
        if extra_table_key and sec.get(extra_table_key):
            parts.append(str(sec.get(extra_table_key)))
        return "\n\n".join(parts).strip()
    return str(sec).strip()

def _normalize(payload: Dict[str, Any]) -> Tuple[str, str, Dict[str, Any], List[str], Dict[str, Any], str, List[Dict[str, str]]]:
    project_id = str(payload.get("project_id", "")).strip()
    title = str(payload.get("page_title") or payload.get("project_title") or payload.get("title") or f"Project Content — {project_id}")

    citations = payload.get("citations") or []
    if not isinstance(citations, list):
        citations = []

    schema_map = {}
    for k in ("schema_org", "schema", "schema_markup"):
        v = payload.get(k)
        if isinstance(v, dict) and v:
            schema_map.update(v)
    if isinstance(payload.get("faq_schema"), dict):
        schema_map["faq_schema"] = payload["faq_schema"]
    if isinstance(payload.get("howto_schema"), dict):
        schema_map["howto_schema"] = payload["howto_schema"]

    combined = str(payload.get("combined_narrative") or "").strip()
    sections = payload.get("sections") or {}
    has_sections = isinstance(sections, dict) and any(
        (isinstance(v, str) and v.strip()) or (isinstance(v, list) and v) for v in sections.values()
    )

    if not has_sections:
        sec_map: Dict[str, Any] = {}
        sec_map["location_connectivity"] = _pluck_md(
            payload.get("location_connectivity") or payload.get("connectivity"), extra_table_key="connectivity_table_md"
        )
        sec_map["unit_mix_floorplans"] = _pluck_md(
            payload.get("unit_mix_floorplans") or payload.get("product_mix_floor_plans")
        )
        sec_map["amenities_lifestyle"] = _pluck_md(
            payload.get("amenities_lifestyle") or payload.get("amenities_specifications"), extra_table_key="amenity_snapshot_table_md"
        )
        sec_map["pricing_payment_notes"] = _pluck_md(payload.get("pricing_payment_notes"))
        sec_map["construction_status_rera"] = _pluck_md(payload.get("construction_status_rera"))
        sec_map["developer_profile_eeat"] = _pluck_md(payload.get("developer_profile"))

        if isinstance(payload.get("nearby_alternatives"), list):
            table = ["| Project | Micro-location | Why consider |", "|---|---|---|"]
            for it in payload["nearby_alternatives"][:8]:
                if not isinstance(it, dict): 
                    continue
                name = str(it.get("name","")).strip()
                loc  = str(it.get("micro_location","")).strip()
                why  = str(it.get("why_consider","")).strip()
                if name:
                    table.append(f"| {name} | {loc} | {why} |")
            sec_map["nearby_alternatives"] = "\n".join(table) if len(table) > 2 else ""
        else:
            sec_map["nearby_alternatives"] = _pluck_md(payload.get("nearby_alternatives"))

        reach = _pluck_md(payload.get("how_to_reach"))
        if reach:
            sec_map["location_connectivity"] = (sec_map.get("location_connectivity","").strip() + "\n\n" + reach).strip()

        faqs_raw = payload.get("faqs") or payload.get("faq") or []
        faqs_norm: List[Dict[str, str]] = []
        if isinstance(faqs_raw, list):
            for item in faqs_raw:
                if not isinstance(item, dict): 
                    continue
                q = item.get("q") or item.get("question") or ""
                a = item.get("a") or item.get("answer") or ""
                if q or a:
                    faqs_norm.append({"q": str(q).strip(), "a": str(a).strip()})
        sec_map["faqs"] = faqs_norm

        sections = sec_map

        if not combined:
            po = payload.get("project_overview")
            if isinstance(po, dict):
                head = po.get("title")
                body = _pluck_md(po)
                comb = []
                if head: 
                    comb.append(f"## {head}")
                if body: 
                    comb.append(body)
                combined = "\n\n".join(comb).strip()

    for k in _SECTION_TITLES:
        sections.setdefault(k, [] if k == "faqs" else "")

    alts_list = payload.get("nearby_alternatives") if isinstance(payload.get("nearby_alternatives"), list) else []

    return title, combined, sections, citations, schema_map, project_id, alts_list  # type: ignore[return-value]


def _render_faqs(faqs: List[Dict[str, Any]]) -> str:
    if not faqs: 
        return ""
    blocks = []
    for item in faqs:
        q = item.get("q") or item.get("question") or ""
        a_md = item.get("a") or item.get("answer") or ""
        q = html.escape(str(q))
        a_html = _md_to_html(str(a_md))
        if not (q or a_html): 
            continue
        blocks.append(f"""
        <details class="faq">
          <summary><strong>{q}</strong></summary>
          <div class="answer">{a_html}</div>
        </details>
        """)
    return "\n".join(blocks)

def _render_nearby_table_if_any(section_text: str, alts_list: List[Dict[str, str]]) -> str:
    has_table = re.search(r"\|.*\|.*\|", section_text or "") is not None
    if has_table or not alts_list:
        return section_text or ""
    table = ["| Project | Micro-location | Why consider |", "|---|---|---|"]
    for it in alts_list[:8]:
        if not isinstance(it, dict): 
            continue
        name = str(it.get("name","")).strip()
        loc  = str(it.get("micro_location","")).strip()
        why  = str(it.get("why_consider","")).strip()
        if name:
            table.append(f"| {name} | {loc} | {why} |")
    if len(table) > 2:
        return (section_text.strip() + "\n\n" + "\n".join(table)).strip()
    return section_text or ""

def _render_citations(citations: List[str]) -> str:
    items = []
    for url in citations or []:
        u = str(url).strip()
        if not u.startswith("http"): 
            continue
        esc = html.escape(u)
        items.append(f'<li><a href="{esc}" rel="nofollow noopener" target="_blank">{esc}</a></li>')
    return "<ul class=\"citations\">\n" + "\n".join(items) + "\n</ul>" if items else ""

def _jsonld_block(obj: Any) -> str:
    try:
        return '<script type="application/ld+json">\n' + json.dumps(obj, ensure_ascii=False, indent=2) + "\n</script>"
    except Exception:
        return ""

CSS = """
:root { --bg:#0b0f14; --panel:#111827; --muted:#9aa4b2; --text:#e5e7eb; --brand:#22c55e; --accent:#60a5fa; }
*{ box-sizing:border-box } html,body{ margin:0; padding:0; background:var(--bg); color:var(--text); font:16px/1.6 system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,"Apple Color Emoji","Segoe UI Emoji" }
.container{ max-width:1024px; margin:0 auto; padding:2rem 1rem 6rem }
.header{ margin-bottom:1.5rem } .header h1{ font-size:1.8rem; margin:0 0 .25rem } .header .meta{ color:var(--muted); font-size:.95rem }
.summary{ border:1px solid #1f2937; background:rgba(34,197,94,.08); padding:1rem; border-radius:.75rem; margin:1rem 0 2rem } .summary strong{ color:var(--brand) }
nav.toc{ background:#0f172a; border:1px solid #1f2937; border-radius:.75rem; padding:.75rem 1rem; margin:1.5rem 0 2rem }
nav.toc a{ color:var(--accent); text-decoration:none; margin-right:1rem }
section{ background:var(--panel); border:1px solid #1f2937; border-radius:.75rem; padding:1.25rem; margin:1rem 0 1.5rem }
section h2{ margin-top:0; font-size:1.25rem } section h3{ font-size:1.05rem }
section table{ width:100%; border-collapse:collapse; margin:.75rem 0 }
section table th,section table td{ border:1px solid #374151; padding:.5rem .6rem; vertical-align:top }
section table th{ background:#0f172a; text-align:left }
.faq details{ border-top:1px dashed #334155; padding:.5rem 0 } .faq summary{ cursor:pointer }
.citations{ margin-top:.5rem } .footer-note{ color:var(--muted); font-size:.9rem; margin-top:2rem }
a{ color:var(--accent) } hr.sep{ border:none; border-top:1px solid #1f2937; margin:2rem 0 }
"""

def _meta_desc(text: str, limit: int = 160) -> str:
    """Trim to a word boundary; drop dangling joiners; add ellipsis only if truncated."""
    t = (text or "").strip()
    if not t:
        return ""
    if len(t) <= limit:
        return t
    # cut at last space before limit
    cut = t[:limit]
    if " " in cut:
        cut = cut[: cut.rfind(" ")]
    cut = re.sub(r"(,?\s*(including|and|with|such as))?$", "", cut, flags=re.I).rstrip(" ,;:-")
    return cut + "…"

def render_payload_to_html(payload: Dict[str, Any], site_name: str = "Square Yards") -> str:
    title, combined_md, sections, citations, schema_map, project_id, alts_list = _normalize(payload)

    aeo_summary_md = str(payload.get("aeo_summary", "")).strip()
    meta_desc = _meta_desc(aeo_summary_md or combined_md, limit=160)

    summary_html = _md_to_html(aeo_summary_md)
    combined_html = _md_to_html(combined_md)

    blocks: List[str] = []
    for key, label in _SECTION_TITLES.items():
        val = sections.get(key)
        if key == "nearby_alternatives":
            val = _render_nearby_table_if_any(str(val or ""), alts_list or [])
        if not val:
            continue
        if key == "faqs" and isinstance(val, list):
            sec_html = _render_faqs(val)
        else:
            sec_html = _md_to_html(str(val))
        blocks.append(f'<section id="section-{key}">\n<h2>{html.escape(label)}</h2>\n{sec_html}\n</section>')

    citations_html = _render_citations(citations)

    jsonld_blocks: List[str] = []
    if isinstance(schema_map, dict):
        for _, v in schema_map.items():
            jsonld_blocks.append(_jsonld_block(v))
    jsonld = "\n".join([b for b in jsonld_blocks if b])

    toc_links = []
    for key, label in _SECTION_TITLES.items():
        if sections.get(key):
            toc_links.append(f'<a href="#section-{key}">{html.escape(label)}</a>')
    toc_html = f'<nav class="toc">{"".join(toc_links)}</nav>' if toc_links else ""

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <meta name="description" content="{html.escape(meta_desc)}" />
  <title>{html.escape(title)}</title>
  <style>{CSS}</style>
  {jsonld}
</head>
<body>
  <div class="container">
    <header class="header">
      <h1>{html.escape(title)}</h1>
      <div class="meta">{html.escape(site_name)} • Project ID: {html.escape(project_id)}</div>
    </header>
    <div class="summary"><strong>AEO Summary:</strong> {summary_html}</div>
    {toc_html}
    <section id="section-combined">
      <h2>Project Overview</h2>
      {combined_html}
    </section>
    {"".join(blocks)}
    <hr class="sep" />
    <section id="section-citations">
      <h2>References & Citations</h2>
      {citations_html or "<p>No citations provided.</p>"}
    </section>
    <p class="footer-note">This page is generated automatically from structured content. Please verify critical facts with official sources before publishing.</p>
  </div>
</body>
</html>
"""