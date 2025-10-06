# src/modeling/generator.py
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam
from pydantic import BaseModel

from src.config import AppConfig
from src.export.schema import CONTENT_JSON_SCHEMA
from src.processing.dedupe import drop_too_similar_sentences
from src.ingest.providers.sy_datacenter_signature import ProjectNorm
from src.modeling.prompt import build_prompt


# ---------------- OpenAI client ----------------
def _get_client() -> OpenAI:
    cfg = AppConfig()
    cfg.validate_keys()
    kwargs: Dict[str, Any] = {}
    if cfg.openai_base_url:
        kwargs["base_url"] = cfg.openai_base_url
    return OpenAI(api_key=cfg.openai_api_key, **kwargs)

def _model_name() -> str:
    return AppConfig().openai_model


# ---------------- Utilities ----------------
def _try_get(obj: Any, *path: str) -> Any:
    cur = obj
    for key in path:
        if cur is None:
            return None
        if isinstance(cur, dict):
            cur = cur.get(key)
        else:
            cur = getattr(cur, key, None)
    return cur

def _domain(u: str) -> str:
    try:
        return urlparse(u).netloc.replace("www.", "")
    except Exception:
        return u

def _fmt_inr(val: Any) -> Optional[str]:
    if val is None:
        return None
    try:
        if isinstance(val, str):
            v = val.replace(",", "").replace("₹", "").strip()
            num = float(v)
        else:
            num = float(val)
        return f"₹{num:,.0f}"
    except Exception:
        return str(val).strip() or None

def _format_bhk_list(bhk: Any) -> List[str]:
    """
    Normalize BHK/typology indicators:
    - 0 -> Studio
    - 1 -> 1 BHK
    - 'Studio' kept as-is
    - removes dupes while keeping order
    """
    out: List[str] = []
    seen = set()
    items: List[str] = []
    if isinstance(bhk, list):
        for b in bhk:
            items.append(str(b).strip())
    elif isinstance(bhk, str):
        items = [x.strip() for x in re.split(r"[,/|]+", bhk) if x.strip()]

    def norm(x: str) -> str:
        lx = x.lower()
        if lx in {"0", "studio", "st", "1rk", "rk"}:
            return "Studio"
        m = re.match(r"^(\d+)\s*bhk$", lx)
        if m:
            return f"{int(m.group(1))} BHK"
        m2 = re.match(r"^(\d+)$", lx)
        if m2:
            return f"{int(m2.group(1))} BHK"
        return x if x else ""

    for it in items:
        n = norm(it)
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out

def _gather_project_facts(project: ProjectNorm) -> Dict[str, Any]:
    facts: Dict[str, Any] = {}
    facts["project_id"] = getattr(project, "project_id", None)
    facts["project_name"] = getattr(project, "project_name", None)
    facts["developer_name"] = getattr(project, "developer_name", None)
    facts["city"] = getattr(project, "city", None)
    facts["locality"] = getattr(project, "locality", None)
    facts["sub_locality"] = getattr(project, "sub_locality", None)
    facts["unit_min_size_sqft"] = getattr(project, "unit_min_size_sqft", None)
    facts["bhk_list"] = _format_bhk_list(getattr(project, "bhk_list", None))
    facts["roads"] = getattr(project, "roads", None)
    facts["price_display"] = getattr(project, "price_display", None)
    facts["price_min"] = getattr(project, "price_min", None)
    facts["price_max"] = getattr(project, "price_max", None)

    dev_obj = _try_get(project, "developer")
    if isinstance(dev_obj, dict):
        facts["developer_years"] = dev_obj.get("experience") or _try_get(project, "developerExperience")
        facts["developer_total_projects"] = dev_obj.get("totalProjects")
        if not facts.get("developer_name"):
            facts["developer_name"] = dev_obj.get("name")
    else:
        facts["developer_years"] = getattr(project, "developer_experience", None) or getattr(project, "developerExperience", None)
        facts["developer_total_projects"] = getattr(project, "developer_total_projects", None)

    sim = getattr(project, "similar_projects", None)
    if not sim:
        raw = getattr(project, "raw", None)
        sim = _try_get(raw, "data", "similarProjects") or []
        if isinstance(sim, list):
            sim = [s.get("projectName") for s in sim if isinstance(s, dict) and s.get("projectName")]
    facts["similar_projects"] = sim or []
    return facts

def _format_evidence(harvest: Dict[str, Any], k: int = 10) -> List[Dict[str, str]]:
    items = (harvest or {}).get("items", [])
    out: List[Dict[str, str]] = []
    for it in items[: max(1, k)]:
        out.append(
            {
                "title": (it.get("title") or "").strip(),
                "url": (it.get("link") or "").strip(),
                "snippet": (it.get("snippet") or "").strip(),
                "domain": (it.get("domain") or "").strip(),
                "query": (it.get("query") or "").strip(),
                "type": (it.get("type") or "organic"),
            }
        )
    return out

def _format_examples(examples: List[Dict[str, str]], max_chars: int = 12000) -> str:
    if not examples:
        return ""
    chunks: List[str] = []
    total = 0
    for ex in examples[:10]:
        head = f"# {ex.get('title','Example')}\n"
        notes = ex.get("style_notes")
        wc = ex.get("word_count")
        notes_txt = f"Style notes: {notes}\nWord count: {wc}\n" if notes else ""
        body = (ex.get("body") or "").strip()
        block = head + notes_txt + body + "\n\n"
        if total + len(block) > max_chars:
            break
        chunks.append(block)
        total += len(block)
    return "\n".join(chunks).strip()


# ----- Section keys & helpers -----
_SECTION_KEYS = [
    "who_is_it_for",
    "location_connectivity",
    "unit_mix_floorplans",
    "amenities_lifestyle",
    "pricing_payment_notes",
    "construction_status_rera",
    "developer_profile_eeat",
    "nearby_alternatives",
    "faqs",
]

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

def _coerce_sections_any(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        out = dict(raw)
    else:
        out = {}
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict) and item.get("key") and item.get("content"):
                    out[str(item["key"])] = _pluck_md(item.get("content"))
    for key in _SECTION_KEYS:
        out.setdefault(key, [] if key == "faqs" else "")
    return out

def _harvest_alternate_into_canonical(data: Dict[str, Any]) -> Dict[str, Any]:
    sec = data.get("sections")
    has_any = False
    if isinstance(sec, dict):
        for v in sec.values():
            if (isinstance(v, str) and v.strip()) or (isinstance(v, list) and v):
                has_any = True
                break
    if has_any:
        return data

    src = data
    mapped: Dict[str, Any] = {}

    mapped["location_connectivity"] = _pluck_md(
        src.get("location_connectivity") or src.get("connectivity"), extra_table_key="connectivity_table_md"
    )
    mapped["unit_mix_floorplans"] = _pluck_md(
        src.get("unit_mix_floorplans") or src.get("product_mix_floor_plans")
    )
    mapped["amenities_lifestyle"] = _pluck_md(
        src.get("amenities_lifestyle") or src.get("amenities_specifications"), extra_table_key="amenity_snapshot_table_md"
    )
    mapped["pricing_payment_notes"] = _pluck_md(src.get("pricing_payment_notes"))
    mapped["construction_status_rera"] = _pluck_md(src.get("construction_status_rera"))
    mapped["developer_profile_eeat"] = _pluck_md(src.get("developer_profile"))

    if isinstance(src.get("nearby_alternatives"), list):
        table = ["| Project | Micro-location | Why consider |", "|---|---|---|"]
        for it in src["nearby_alternatives"][:8]:
            if not isinstance(it, dict): 
                continue
            name = str(it.get("name","")).strip()
            loc  = str(it.get("micro_location","")).strip()
            why  = str(it.get("why_consider","")).strip()
            if name:
                table.append(f"| {name} | {loc} | {why} |")
        mapped["nearby_alternatives"] = "\n".join(table) if len(table) > 2 else ""
    else:
        mapped["nearby_alternatives"] = _pluck_md(src.get("nearby_alternatives"))

    reach = _pluck_md(src.get("how_to_reach"))
    if reach:
        mapped["location_connectivity"] = (mapped.get("location_connectivity","").strip() + "\n\n" + reach).strip()

    if not mapped.get("faqs"):
        faqs = src.get("faqs") or src.get("faq") or []
        if isinstance(faqs, list):
            mapped["faqs"] = [{"q": (it.get("q") or it.get("question") or "").strip(),
                               "a": (it.get("a") or it.get("answer") or "").strip()}
                              for it in faqs if isinstance(it, dict)]
        else:
            mapped["faqs"] = []

    for k in _SECTION_KEYS:
        mapped.setdefault(k, [] if k == "faqs" else "")

    data["sections"] = mapped

    if not data.get("combined_narrative"):
        po = src.get("project_overview")
        if isinstance(po, dict):
            head = po.get("title")
            body = _pluck_md(po)
            comb = []
            if head: 
                comb.append(f"## {head}")
            if body: 
                comb.append(body)
            data["combined_narrative"] = "\n\n".join(comb).strip()
    return data

def _swap_unit_vs_amenities_if_misplaced(sections: Dict[str, Any]) -> Dict[str, Any]:
    u = sections.get("unit_mix_floorplans", "") or ""
    a = sections.get("amenities_lifestyle", "") or ""
    u_has_amenity = re.search(r"(?i)\bamenit|club|leisure|games|pool|green\b", u) is not None
    a_has_unit   = re.search(r"(?i)\bunit|carpet|layout|floor|stack|facing\b", a) is not None
    if u_has_amenity and a_has_unit:
        sections["unit_mix_floorplans"], sections["amenities_lifestyle"] = a, u
    return sections

_SHORT_ANSWER_PREFIX = re.compile(r"(?i)\bshort\s*answer\s*\([^)]*\)\s*:\s*")
_RERA_LINE = re.compile(r"(?im)^(?=.*\bRERA\b|HRERA\b).+$")
_GENERIC_LINE = re.compile(
    r"(?i)^\-+\s*(seek an all\-in|confirm possession|compare maintenance|ask for references|look for a minimum|verification steps|smart budgeting checklist)\b"
)

def _strip_short_answer(s: str) -> str:
    return _SHORT_ANSWER_PREFIX.sub("", s or "")

def _clean_rera_noise(section_key: str, text: str) -> str:
    if section_key in {"construction_status_rera"}:
        return text
    cleaned = []
    for line in (text or "").splitlines():
        if _RERA_LINE.search(line):
            if section_key == "pricing_payment_notes" and ("payment" in line.lower() or "escrow" in line.lower()):
                cleaned.append(line)
            continue
        cleaned.append(line)
    return "\n".join(cleaned).strip()

def _anti_generic(text: str) -> str:
    if not text:
        return text
    out = []
    for line in text.splitlines():
        if _GENERIC_LINE.search(line.strip()):
            continue
        out.append(line)
    return "\n".join(out).strip()

def _normalize_faqs(faqs: Any) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    if isinstance(faqs, list):
        for item in faqs:
            if not isinstance(item, dict):
                continue
            q = item.get("q") or item.get("question") or ""
            a = item.get("a") or item.get("answer") or ""
            if q or a:
                out.append({"q": str(q).strip(), "a": str(a).strip()})
    return out[:10]

def _force_aeo_length(text: str, min_w: int = 40, max_w: int = 60) -> str:
    words = re.findall(r"\b\w[\w’']*\b", text or "")
    if not words:
        return ""
    if len(words) <= max_w and len(words) >= min_w:
        return text.strip().rstrip(".") + "."
    trimmed = " ".join(words[:max_w])
    return trimmed.strip().rstrip(".") + "."

# ---- Citation hygiene ----
_OBJ_CITE_RE = re.compile(r"\[\s*\{[^{}]*?\"id\"\s*:\s*(\d{1,2})[^{}]*?\}\s*\]")
_BRACKET_CITE_RE = re.compile(r"\[(\d{1,2})\]")

def _replace_citation_objects(text: str) -> str:
    return _OBJ_CITE_RE.sub(lambda m: f"[{m.group(1)}]", text or "")

def _max_citation_index_in_text(text: str) -> int:
    mx = 0
    for m in _BRACKET_CITE_RE.finditer(text or ""):
        try:
            mx = max(mx, int(m.group(1)))
        except Exception:
            pass
    return mx

def _merge_citations_seed(project_url: Optional[str], existing: List[str], evidence_urls: List[str], cap: int = 8) -> List[str]:
    out: List[str] = []
    def add(u: Optional[str]):
        if not u or not isinstance(u, str): 
            return
        u = u.strip()
        if not u.startswith("http"): 
            return
        if u not in out:
            out.append(u)
    add(project_url)
    for u in existing or []:
        add(u)
        if len(out) >= cap: 
            return out[:cap]
    for u in evidence_urls or []:
        add(u)
        if len(out) >= cap: 
            return out[:cap]
    return out[:cap]

def _expand_source_brackets(text: str, citations: List[str]) -> str:
    if not text:
        return text
    def repl(m):
        idx = int(m.group(1)) - 1
        if 0 <= idx < len(citations):
            return f"[{_domain(citations[idx])}]"
        return ""
    return re.sub(r"\[(\d{1,2})\]", repl, text)

def _strip_leading_heading(md: str) -> str:
    if not isinstance(md, str):
        return ""
    lines = md.strip().splitlines()
    if lines and re.match(r"^\s*#{2,3}\s+", lines[0]):
        return "\n".join(lines[1:]).lstrip()
    return md

def _synthesize_combined_from_sections(project: ProjectNorm, sections: Dict[str, Any]) -> str:
    parts: List[str] = []
    title_line = f"# {project.project_name or 'Project Overview'}"
    if project.locality or project.city:
        loc = ", ".join([x for x in [project.locality, project.city] if x])
        title_line += f" — {loc}"
    parts.append(title_line)
    order = [
        "who_is_it_for",
        "location_connectivity",
        "unit_mix_floorplans",
        "amenities_lifestyle",
        "pricing_payment_notes",
        "construction_status_rera",
        "developer_profile_eeat",
        "nearby_alternatives",
    ]
    for key in order:
        val = sections.get(key)
        if isinstance(val, str) and val.strip():
            label = key.replace("_", " ").title().replace("Eeat", "E-E-A-T")
            body = _strip_leading_heading(val)
            parts.append(f"## {label}\n{body.strip()}")
    return "\n\n".join(parts).strip()


# ---- Heuristic amenity synthesis from SERP (when DC is empty) ----
_AMENITY_PATTERNS = {
    "Sports & Fitness": r"\bgym|fitness|yoga|jog|jogging|cycle|cycling|court|football|tennis|pool|billiards|snooker|basketball\b",
    "Kids": r"\bkids|children|play area|sand pit|toddler\b",
    "Community & Leisure": r"\bclub|indoor games|cafe|coffee|retail|multipurpose|banquet|conference|theatre|library\b",
    "Safety": r"\bsecurity|cctv|surveillance|access control|video door|guard\b",
    "Essentials": r"\bpower backup|generator|lift|water supply|stp|waste|parking\b",
    "Environment": r"\bcentral green|park|landscap|garden|green\b",
}

def _amenities_from_evidence(evidence: List[Dict[str, str]]) -> str:
    buckets: Dict[str, List[str]] = {k: [] for k in _AMENITY_PATTERNS}
    for ev in evidence:
        text = f"{ev.get('title','')} {ev.get('snippet','')}".lower()
        for k, rx in _AMENITY_PATTERNS.items():
            if re.search(rx, text):
                # capture a simple token for k
                if "gym" in text and "Sports & Fitness" in buckets:
                    if "Gym" not in buckets["Sports & Fitness"]:
                        buckets["Sports & Fitness"].append("Gym")
                if "yoga" in text and "Sports & Fitness" in buckets:
                    if "Yoga zone" not in buckets["Sports & Fitness"]:
                        buckets["Sports & Fitness"].append("Yoga zone")
                if "cctv" in text and "Safety" in buckets:
                    if "CCTV" not in buckets["Safety"]:
                        buckets["Safety"].append("CCTV")
                # ... we only need a few; rest are implied by pattern
    rows = []
    for cat, items in buckets.items():
        if items:
            rows.append([cat, ", ".join(items[:8])])
    if not rows:
        return ""
    return "**Amenity snapshot**\n\n" + _mk_table(rows, ["Category", "Key inclusions"])


# ---------------- Deterministic fallback from Datacenter ----------------
def _mk_table(rows: List[List[str]], headers: List[str]) -> str:
    if not rows:
        return ""
    out = [f"| {' | '.join(headers)} |", f"|{'|'.join(['---']*len(headers))}|"]
    for r in rows:
        out.append(f"| {' | '.join([str(c) for c in r])} |")
    return "\n".join(out)

def _fill_from_datacenter(project: ProjectNorm) -> Dict[str, str]:
    out: Dict[str, str] = {k: "" for k in _SECTION_KEYS if k != "faqs"}

    who_bits: List[str] = []
    bhk_list = _format_bhk_list(getattr(project, "bhk_list", None))
    if bhk_list:
        who_bits.append(f"Best suited for {', '.join(bhk_list)} families")
    if getattr(project, "unit_min_size_sqft", None):
        who_bits.append(f"entry carpet ~{project.unit_min_size_sqft} sq ft")
    loc = ", ".join([x for x in [getattr(project, 'locality', None), getattr(project, 'city', None)] if x])
    if loc:
        who_bits.append(f"located in {loc}")
    if who_bits:
        out["who_is_it_for"] = " • ".join(who_bits) + "."

    rows: List[List[str]] = []
    for r in (getattr(project, "roads", None) or [])[:6]:
        name = str(r.get("name") or r.get("road") or "").strip()
        dist = str(r.get("distance_text") or r.get("distance") or "").strip()
        if name:
            rows.append([name, dist or "-"])
    if rows:
        out["location_connectivity"] = "**Connectivity snapshot**\n\n" + _mk_table(rows, ["Corridor / Landmark", "Approx. distance"])

    unit_bits: List[str] = []
    if bhk_list:
        unit_bits.append(f"Typologies: {', '.join(bhk_list)}.")
    if getattr(project, "unit_min_size_sqft", None):
        unit_bits.append(f"Smallest carpet around ~{project.unit_min_size_sqft} sq ft (as per listing).")
    if unit_bits:
        out["unit_mix_floorplans"] = " ".join(unit_bits)

    amen_rows: List[List[str]] = []
    amcats = getattr(project, "amenities_by_cat", None)
    if isinstance(amcats, dict):
        for cat, items in list(amcats.items())[:6]:
            if items:
                amen_rows.append([str(cat), ", ".join([str(i) for i in items[:8]])])
    if amen_rows:
        out["amenities_lifestyle"] = "**Amenity snapshot**\n\n" + _mk_table(amen_rows, ["Amenity Theme", "Highlights"])

    ppn = ""
    price_display = getattr(project, "price_display", None)
    if price_display:
        ppn = f"**Indicative ticket band:** {price_display} (ex-taxes; confirm latest cost sheet)."
    else:
        mn, mx = getattr(project, "price_min", None), getattr(project, "price_max", None)
        fm, fx = _fmt_inr(mn), _fmt_inr(mx)
        if fm and fx:
            ppn = f"**Indicative ticket band:** {fm} – {fx} (ex-taxes)."
        elif fm or fx:
            ppn = f"**Indicative ticket:** {(fm or fx)} (ex-taxes)."
    out["pricing_payment_notes"] = ppn

    rera_parts: List[str] = []
    if getattr(project, "project_status", None):
        rera_parts.append(f"Current status: {project.project_status}.")
    if getattr(project, "rera_id_primary", None):
        rera_parts.append(f"RERA ID: {project.rera_id_primary}.")
    if getattr(project, "rera_id_project", None):
        rera_parts.append(f"RERA Project: {project.rera_id_project}.")
    if rera_parts:
        out["construction_status_rera"] = " ".join(rera_parts)

    dev_parts: List[str] = []
    dev_name = getattr(project, "developer_name", None)
    if dev_name:
        dev_parts.append(f"Developer: {dev_name}.")
    years = _try_get(project, "developer", "experience") \
            or getattr(project, "developer_experience", None) \
            or getattr(project, "developerExperience", None)
    if years:
        dev_parts.append(f"Approx. years of execution: {years}+.")
    sim = getattr(project, "similar_projects", None) or []
    if sim:
        dev_parts.append("\n" + _mk_table([[str(nm), "-"] for nm in sim[:5]], ["Developer portfolio (sample)", "Notes"]))
    out["developer_profile_eeat"] = "\n\n".join([p for p in dev_parts if p])

    if sim:
        out["nearby_alternatives"] = _mk_table(
            [[str(nm), getattr(project, "city", None) or "-", "Same micro-market"] for nm in sim[:5]],
            ["Project", "City", "Why consider"]
        )

    return out


# ---------------- Result ----------------
class GenerationResult(BaseModel):
    payload: Dict[str, Any]


# --------- Section expansion (second pass) ----------
_MIN_WORDS = {
    "who_is_it_for": 120, "location_connectivity": 150, "unit_mix_floorplans": 150,
    "amenities_lifestyle": 140, "pricing_payment_notes": 140,
    "construction_status_rera": 120, "developer_profile_eeat": 160,
    "nearby_alternatives": 140,
}
_MAX_WORDS = {
    "who_is_it_for": 220, "location_connectivity": 220, "unit_mix_floorplans": 220,
    "amenities_lifestyle": 220, "pricing_payment_notes": 200,
    "construction_status_rera": 180, "developer_profile_eeat": 230,
    "nearby_alternatives": 200,
}
def _needs_more_words(text: str, min_words: int) -> bool:
    return len(re.findall(r"\b\w[\w’']*\b", text or "")) < min_words

def _expand_with_llm(client: OpenAI, model: str, section_key: str, seed: str, project_ctx: Dict[str, Any], evidence_text: str) -> str:
    """Ask model to enrich a single section within strict constraints."""
    prompt = (
        "You will rewrite and expand ONE section of a real-estate PDP.\n"
        f"Section key: `{section_key}`.\n"
        "Constraints:\n"
        f"- Target length: {_MIN_WORDS[section_key]}–{_MAX_WORDS[section_key]} words.\n"
        "- Be specific to the project/locality; avoid generic checklists.\n"
        "- Do not mention 'Short answer'.\n"
        "- Keep RERA mentions only for construction/pricing safety.\n"
        "- If data is missing, use relevant hints from the evidence; do not invent facts.\n"
        "- Keep any tables or lists in valid Markdown.\n\n"
        f"Project context (JSON): {json.dumps(project_ctx, ensure_ascii=False)}\n"
        f"Evidence (top snippets):\n{evidence_text}\n\n"
        f"Seed text (to refine/expand):\n{seed}\n\n"
        "Return ONLY the final Markdown for this section."
    )
    try:
        r = client.responses.create(model=model, input=prompt)
        txt = getattr(r, "output_text", None)
        if txt: 
            return txt.strip()
    except Exception:
        msgs: List[ChatCompletionMessageParam] = [
            {"role": "system", "content": "Return only Markdown text for the section."},
            {"role": "user", "content": prompt},
        ]
        comp = client.chat.completions.create(model=model, messages=msgs)
        txt = comp.choices[0].message.content or ""
        return txt.strip()
    return seed


# ---------------- Main generation ----------------
def generate_project_content(
    project: ProjectNorm,
    harvest: Dict[str, Any],
    no_repeat: List[str],
    examples: List[Dict[str, str]] | None = None,
    top_k_sources: int = 10,
) -> GenerationResult:

    client = _get_client()
    model = _model_name()

    guidelines = (
        "Rules:\n"
        "- Start with a 40–60 word direct answer (AEO).\n"
        "- Keep facts traceable; do not invent.\n"
        "- Do not repeat PDP literals verbatim; paraphrase labels.\n"
        "- Use H2/H3 question-led structure; include a concise FAQ.\n"
        "- Conversational but precise; avoid hype.\n"
    )
    evidence = _format_evidence(harvest, k=top_k_sources)
    examples_text = _format_examples(examples or [])
    facts = _gather_project_facts(project)

    project_ctx = {
        "project_id": project.project_id,
        "project_name": project.project_name,
        "developer_name": facts.get("developer_name"),
        "developer_years": facts.get("developer_years"),
        "developer_total_projects": facts.get("developer_total_projects"),
        "city": project.city,
        "locality": project.locality,
        "sub_locality": facts.get("sub_locality"),
        "status": project.project_status,
        "price_display": facts.get("price_display"),
        "price_min_inr": facts.get("price_min"),
        "price_max_inr": facts.get("price_max"),
        "bhk_list": facts.get("bhk_list"),
        "unit_min_size_sqft": project.unit_min_size_sqft,
        "rera_primary": project.rera_id_primary,
        "rera_project": project.rera_id_project,
        "lat": project.lat,
        "lon": project.lon,
        "roads": project.roads,
        "amenities_by_cat": project.amenities_by_cat,
        "project_url": project.project_url,
        "similar_projects": facts.get("similar_projects"),
    }

    no_repeat_joined = "; ".join([s for s in (no_repeat or []) if s])[:4000]
    evidence_lines = [
        f"{i}. {ev.get('title','').strip()} — {ev.get('snippet','').strip()} "
        f"({ev.get('domain','')}) <{ev.get('url','')}>"
        for i, ev in enumerate(evidence, start=1)
    ]
    prompt_str = build_prompt(
        project_ctx=project_ctx,
        guidelines_text=guidelines,
        evidence_lines=evidence_lines,
        examples_text=examples_text,
        no_repeat_joined=no_repeat_joined,
    )

    # Call LLM — Responses API primary; JSON Chat fallback
    def _call_llm_for_json(prompt: str) -> Dict[str, Any]:
        try:
            resp = client.responses.create(model=model, input=prompt)
            txt: Optional[str] = getattr(resp, "output_text", None)
            if txt:
                return json.loads(txt)
            pieces: List[str] = []
            for out in getattr(resp, "output", []) or []:
                for c in getattr(out, "content", []) or []:
                    t = getattr(c, "text", None)
                    if t:
                        pieces.append(str(t))
            if pieces:
                return json.loads("".join(pieces).strip())
        except Exception:
            messages: List[ChatCompletionMessageParam] = [
                {"role": "system", "content": "Return ONLY valid JSON that follows the provided schema."},
                {"role": "user", "content": prompt},
            ]
            comp = client.chat.completions.create(
                model=model, messages=messages, response_format={"type": "json_object"}
            )
            text = comp.choices[0].message.content or "{}"
            return json.loads(text)
        raise RuntimeError("LLM did not return parseable JSON.")

    data: Dict[str, Any] = _call_llm_for_json(prompt_str)

    # ---- Core defaults
    data.setdefault("project_id", project.project_id)
    data.setdefault("sections", {})
    evidence_urls = [e["url"] for e in evidence if e.get("url")]
    seeded_citations = _merge_citations_seed(getattr(project, "project_url", None), data.get("citations") or [], evidence_urls)
    data["citations"] = seeded_citations

    # Title fallback
    if "page_title" not in data or not str(data.get("page_title")).strip():
        loc = ", ".join([x for x in [project.locality, project.city] if x])
        data["page_title"] = f"{project.project_name}, {loc}".strip(", ")

    # AEO summary (length & sanitize)
    aeo = _replace_citation_objects(str(data.get("aeo_summary", "") or ""))
    data["aeo_summary"] = _force_aeo_length(_strip_short_answer(aeo))

    # Harvest alternates into canonical if canonical are blank
    data = _harvest_alternate_into_canonical(data)

    # Coerce & sanitize sections
    sections_raw = data.get("sections") or {}
    sections = _coerce_sections_any(sections_raw)
    fixed: Dict[str, Any] = {}
    banlist = no_repeat or []
    for key in _SECTION_KEYS:
        val = sections.get(key, "" if key != "faqs" else [])
        if key == "faqs":
            fixed[key] = _normalize_faqs(val)
        else:
            txt = _replace_citation_objects(str(val or ""))
            txt = _strip_short_answer(txt)
            txt = drop_too_similar_sentences(txt, banlist)
            txt = _clean_rera_noise(key, txt)
            txt = _anti_generic(txt)
            fixed[key] = txt
    sections = _swap_unit_vs_amenities_if_misplaced(fixed)

    # ---- Per-section fallback: fill any empty section from Datacenter
    auto = _fill_from_datacenter(project)
    for k, v in auto.items():
        current = sections.get(k)
        if not (isinstance(current, str) and current.strip()):
            sections[k] = v

    # ---- If amenities still blank, synthesize from evidence
    if not sections.get("amenities_lifestyle"):
        synth = _amenities_from_evidence(evidence)
        if synth:
            sections["amenities_lifestyle"] = synth

    # ---- Second pass: expand thin sections to target word counts
    ev_text = "\n".join(f"- {e.get('title','')} — {e.get('snippet','')} <{e.get('url','')}>" for e in evidence[:12])
    for key in _MIN_WORDS.keys():
        cur = sections.get(key, "")
        if _needs_more_words(cur, _MIN_WORDS[key]):
            sections[key] = _expand_with_llm(client, model, key, cur, project_ctx, ev_text)

    data["sections"] = sections

    # Combined narrative (synthesize if empty/too short) and citation token cleanup
    combined = _replace_citation_objects(str(data.get("combined_narrative", "") or ""))
    combined = drop_too_similar_sentences(combined, banlist)
    if not isinstance(combined, str) or len(re.findall(r"\b\w[\w’']*\b", combined)) < 750:
        combined = _synthesize_combined_from_sections(project, sections)
    data["combined_narrative"] = _expand_source_brackets(combined, data["citations"])

    # --- Ensure we have enough URLs for all [n] tokens used anywhere
    texts_for_index = [data.get("aeo_summary",""), data["combined_narrative"]] + [sections.get(k,"") for k in _SECTION_KEYS if k != "faqs"]
    max_idx = 0
    for t in texts_for_index:
        max_idx = max(max_idx, _max_citation_index_in_text(str(t or "")))
    if max_idx > len(data["citations"]):
        for u in evidence_urls:
            if u not in data["citations"]:
                data["citations"].append(u)
            if len(data["citations"]) >= max_idx:
                break
    if len(data["citations"]) < 3:
        for u in evidence_urls:
            if u not in data["citations"]:
                data["citations"].append(u)
            if len(data["citations"]) >= 3:
                break
    data["citations"] = data["citations"][:8]

    # Validate final payload
    required = []
    if isinstance(CONTENT_JSON_SCHEMA, dict):
        required = CONTENT_JSON_SCHEMA.get("required", []) or []
    required = required or ["project_id", "aeo_summary", "combined_narrative", "sections"]
    for key in required:
        if key not in data:
            raise RuntimeError(f"Model did not return required key: {key}")

    return GenerationResult(payload=data)


def generate_to_file(
    project: ProjectNorm,
    harvest: Dict[str, Any],
    no_repeat: List[str],
    examples: List[Dict[str, str]] | None,
    out_path: str | Path,
) -> Path:
    res = generate_project_content(project, harvest, no_repeat, examples)
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(res.payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return p