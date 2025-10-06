from __future__ import annotations
from typing import List
from src.ingest.providers.sy_datacenter_signature import ProjectNorm

def build_query_plan(p: ProjectNorm) -> List[str]:
    """
    Queries designed for Indian residential context, using RERA + locality + corridors.
    """
    q: List[str] = []
    if p.project_name and p.city:
        q.append(f"{p.project_name} {p.city}")
    if p.project_name and p.locality:
        q.append(f"{p.project_name} {p.locality}")
    if p.developer_name and p.city:
        q.append(f"{p.developer_name} {p.city} new launch")

    # RERA details drive trust; include both variants if present
    if p.rera_id_project:
        q += [f"{p.project_name} RERA {p.rera_id_project}", f"{p.rera_id_project} RERA details"]
    if p.rera_id_primary:
        q += [f"{p.project_name} RERA {p.rera_id_primary}", f"{p.rera_id_primary} RERA details"]

    # Attribute questions that map to sections/FAQs
    if p.project_name and p.city:
        q += [
            f"{p.project_name} possession date {p.city}",
            f"{p.project_name} amenities {p.city}",
            f"{p.project_name} floor plan {p.city}",
            f"{p.project_name} construction status {p.city}",
            f"{p.project_name} location connectivity {p.city}",
        ]

    # Corridor/road intent from PDP (NH 8, SPR, etc.)
    for r in p.roads:
        nm = r.get("name")
        if nm:
            q.append(f"{p.project_name} near {nm}")

    # Alternatives by locality/corridor (for 'nearby_alternatives')
    if p.locality and p.city:
        q += [f"best new projects in {p.locality} {p.city}",
              f"{p.city} {p.locality} premium apartments"]

    # De-dupe preserving order
    seen = set()
    out = []
    for item in q:
        if item not in seen:
            out.append(item)
            seen.add(item)
    return out