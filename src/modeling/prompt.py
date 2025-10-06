# src/modeling/prompt.py
from __future__ import annotations
import json
from typing import Dict, List

def build_prompt(
    project_ctx: Dict[str, object],
    guidelines_text: str,
    evidence_lines: List[str],
    examples_text: str,
    no_repeat_joined: str,
) -> str:
    """
    Central prompt template for PDP content generation with strong anti-generic controls,
    explicit length targets, and section-specific requirements.
    """

    system = (
        "You are a senior India real-estate content strategist. "
        "Write long-form PDP content that is people-first, specific, and obviously expert."
    )

    hard_rules = (
        "Output rules:\n"
        "- NEVER print the literal words 'Short answer' anywhere.\n"
        "- Provide ONE 40–60 word direct-answer summary at the very top in `aeo_summary` (plain text, 1–2 sentences).\n"
        "- In all sections, the first paragraph should be a crisp lead-in (no labels like 'Short answer').\n"
        "- Mention RERA/HRERA only in `construction_status_rera` and (once) in `pricing_payment_notes` for pricing safety.\n"
        "- Use ONLY project specifics from `project_ctx` + SERP evidence. Avoid boilerplate and generic checklists.\n"
        "- Include at least one Markdown table (e.g., Connectivity/Distances; Amenity snapshot) when corresponding data exists.\n"
        "- Developer Profile must include: developer name, years active (if available), regions of operation, and any recognitions/evidence-backed highlights.\n"
        "- Nearby Alternatives must list 3–5 named projects; prefer `project_ctx.similar_projects`, else use evidence.\n"
        "- Combined narrative length target: 900–1200 words overall; do not go below 750 words.\n"
        "- Each of these sections should be 120–220 words: "
        "`who_is_it_for`, `location_connectivity`, `unit_mix_floorplans`, `amenities_lifestyle`, "
        "`pricing_payment_notes`, `construction_status_rera`, `developer_profile_eeat`, `nearby_alternatives`.\n"
        "- Provide 3–8 credible citations and actually reference them in the text as [1], [2], etc.\n"
        "- Follow the JSON schema exactly. Return only JSON.\n"
    )

    ctx_hints = (
        "Project context hints (always use when writing):\n"
        "- Name: {project_name} | City: {city} | Locality/Sub-location: {locality}\n"
        "- Roads with distances (table when available): {roads}\n"
        "- Minimum unit size (sq ft): {unit_min_size_sqft}\n"
        "- BHK/Typology indicators: {bhk_list}\n"
        "- Developer: {developer_name}; years active: {developer_years}; total projects: {developer_total_projects}\n"
        "- Similar projects to mention: {similar_projects}\n"
        "- If a price band exists, weave it once in `pricing_payment_notes`, not everywhere.\n"
    ).format(
        project_name=project_ctx.get("project_name"),
        city=project_ctx.get("city"),
        locality=f"{project_ctx.get('locality')} | Sector: {project_ctx.get('sub_locality')}",
        roads=project_ctx.get("roads"),
        unit_min_size_sqft=project_ctx.get("unit_min_size_sqft"),
        bhk_list=project_ctx.get("bhk_list"),
        developer_name=project_ctx.get("developer_name"),
        developer_years=project_ctx.get("developer_years"),
        developer_total_projects=project_ctx.get("developer_total_projects"),
        similar_projects=project_ctx.get("similar_projects"),
    )

    constraints = (
        "Duplication guard:\n"
        f"- Do NOT restate these PDP literals verbatim: {no_repeat_joined}\n"
        "- Paraphrase any overlapping facts; prefer synthesis over repetition.\n"
        "- Avoid generic checklists and disclaimers. Every sentence must be project- or locality-specific.\n"
    )

    prompt = (
        f"<SYSTEM>\n{system}\n</SYSTEM>\n\n"
        "<USER>\n"
        "Task:\n"
        "Generate PDP content as structured JSON compliant with our schema.\n\n"
        f"{guidelines_text}\n\n"
        "Context (normalized from Square Yards Datacenter):\n"
        f"{json.dumps(project_ctx, ensure_ascii=False)}\n\n"
        "Top evidence (from SERP):\n"
        + "\n".join(evidence_lines[:12]) + "\n\n"
        "Human-written style references (tone only):\n"
        f"{examples_text if examples_text else '(none)'}\n\n"
        f"{hard_rules}\n"
        f"{ctx_hints}\n"
        f"{constraints}\n"
        "</USER>"
    )
    return prompt