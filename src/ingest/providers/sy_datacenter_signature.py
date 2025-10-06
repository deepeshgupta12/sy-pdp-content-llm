from __future__ import annotations
from typing import Any, Dict, List, Optional
from pathlib import Path

import json
from pydantic import BaseModel, Field, ConfigDict


# --- Pydantic models that accept the exact wrapper you shared ---
class ProjectData(BaseModel):
    # Keep it permissive; we only pick what we need.
    model_config = ConfigDict(extra="allow")

class DataBlock(BaseModel):
    projectId: str | int
    projectData: ProjectData

class SYDatacenterEnvelope(BaseModel):
    status: int
    message: str
    data: DataBlock


def load_sy_datacenter_json(path: str | Path) -> SYDatacenterEnvelope:
    """Load the exact SY Datacenter wrapper (status/message/data.projectData)."""
    p = Path(path)
    raw = json.loads(p.read_text("utf-8"))
    return SYDatacenterEnvelope.model_validate(raw)


# --- Canonical normalized model used downstream by the generator ---
class ProjectNorm(BaseModel):
    project_id: str
    project_name: Optional[str] = None
    developer_name: Optional[str] = None
    city: Optional[str] = None
    locality: Optional[str] = None       # e.g., Sector 71
    micromarket: Optional[str] = None    # optional
    project_status: Optional[str] = None # e.g., New Launch, Under Construction
    price_display: Optional[str] = None  # e.g., "4.09 Cr to 7.31 Cr"
    price_min: Optional[float] = None
    price_max: Optional[float] = None
    currency: Optional[str] = "INR"
    bhk_list: Optional[List[str]] = None # e.g., ["3 BHK","4 BHK"]
    unit_min_size_sqft: Optional[int] = None
    rera_id_primary: Optional[str] = None       # sqyRera
    rera_id_project: Optional[str] = None       # projectReraData[0].ReraProjectNumber
    lat: Optional[float] = None
    lon: Optional[float] = None
    project_url: Optional[str] = None
    roads: List[Dict[str, str]] = Field(default_factory=list)  # [{"name","distance"}]
    amenities_by_cat: List[Dict[str, Any]] = Field(default_factory=list)
    images: List[Dict[str, Any]] = Field(default_factory=list)
    seo_html: Optional[str] = None
    description_html: Optional[str] = None
    seousp_html: Optional[str] = None
    developer_experience_years: Optional[int] = None
    extras: Dict[str, Any] = Field(default_factory=dict)


# --- Helpers ---
def _parse_price_text_to_inr_range(price_text: Optional[str]) -> tuple[Optional[float], Optional[float]]:
    """
    "4.09 Cr to 7.31 Cr" -> (40900000.0, 73100000.0)
    Handles Cr/Lakh formats.
    """
    if not price_text:
        return (None, None)
    import re
    nums = re.findall(r"([\d.,]+)\s*(Cr|Lac|Lakh)?", price_text, flags=re.I)
    vals = []
    for n, unit in nums:
        try:
            base = float(n.replace(",", ""))
        except Exception:
            continue
        unit = (unit or "").lower()
        mult = 1.0
        if unit in ("cr",):
            mult = 1e7
        elif unit in ("lac", "lakh"):
            mult = 1e5
        vals.append(base * mult)
    if not vals:
        return (None, None)
    if len(vals) == 1:
        return (vals[0], vals[0])
    return (min(vals), max(vals))


def _derive_developer_name(project_name: Optional[str]) -> Optional[str]:
    """
    Heuristic: many SY names include the developer prefix (e.g., 'Signature Global Cloverdale').
    Grab the first 1–2 tokens if they look like a known developer pattern.
    """
    if not project_name:
        return None
    tokens = project_name.split()
    if len(tokens) >= 2 and tokens[0].lower() in {"signature", "godrej", "dlf", "sobha", "prestige"}:
        # "Signature Global Cloverdale" -> "Signature Global"
        return " ".join(tokens[:2]) if tokens[0].lower() == "signature" and tokens[1].lower() == "global" else tokens[0].title()
    return None


def _bhk_list_from_fields(sizes: Optional[str], unit_min_bedroom_count: Optional[str]) -> List[str] | None:
    """
    Accept "3 BHK-4 BHK" or "3,4 BHK" and return standardized list ["3 BHK","4 BHK"].
    """
    import re
    texts = [sizes or "", unit_min_bedroom_count or ""]
    combined = " ".join(texts)
    found = re.findall(r"(\d+(\.\d+)?)\s*BHK", combined, flags=re.I)
    if not found:
        # Sometimes "3,4 BHK"
        alt = re.findall(r"(\d+(\.\d+)?)(?=,|\s|$)", combined)
        if not alt:
            return None
        uniq = sorted({f"{a[0]} BHK" for a in alt})
        return uniq
    uniq = sorted({f"{a[0]} BHK" for a in found})
    return uniq or None


def map_sy_envelope_to_norm(env: SYDatacenterEnvelope) -> ProjectNorm:
    d = env.data.projectData.model_dump()

    project_id = str(env.data.projectId)
    project_name = d.get("projectName")
    city = d.get("city")
    locality = d.get("subLocation") or d.get("location")
    status = d.get("status")
    price_display = d.get("priceText")
    price_min, price_max = _parse_price_text_to_inr_range(price_display)
    currency = "INR"  # SY uses ₹ + text; we normalize to INR.

    bhk_list = _bhk_list_from_fields(d.get("sizes"), d.get("unitMinBedroomCount"))
    unit_min_size = d.get("unitMinSize")

    # RERA sources
    rera_primary = d.get("sqyRera")
    rera_project = None
    prj_rera_data = d.get("projectReraData") or []
    if isinstance(prj_rera_data, list) and prj_rera_data:
        rera_project = (prj_rera_data[0] or {}).get("ReraProjectNumber") or None

    # Roads (distance/name)
    roads = []
    for r in d.get("roads") or []:
        nm = r.get("name")
        dist = str(r.get("distance")) if r.get("distance") is not None else ""
        if nm:
            roads.append({"name": nm, "distance": dist})

    # Amenities grouped by category
    amenities_by_cat = []
    for cat in d.get("amenities") or []:
        amenities_by_cat.append({
            "category": cat.get("category"),
            "amenity": [a.get("name") for a in (cat.get("amenity") or []) if a.get("name")]
        })

    # Images (we keep minimal, but preserve master-plan descriptions: handy for facts)
    images = []
    for im in d.get("images") or []:
        images.append({
            "name": im.get("name"),
            "type": im.get("type"),
            "url": im.get("url"),
            "alt": im.get("altTag"),
            "description": im.get("description")
        })

    dev_name = _derive_developer_name(project_name) or None

    return ProjectNorm(
        project_id=project_id,
        project_name=project_name,
        developer_name=dev_name,
        city=city,
        locality=locality,
        micromarket=None,
        project_status=status,
        price_display=price_display,
        price_min=price_min,
        price_max=price_max,
        currency=currency,
        bhk_list=bhk_list,
        unit_min_size_sqft=unit_min_size,
        rera_id_primary=rera_primary,
        rera_id_project=rera_project,
        lat=d.get("latitude"),
        lon=d.get("longitude"),
        project_url=d.get("projectUrl") or (d.get("metaData") or {}).get("url"),
        roads=roads,
        amenities_by_cat=amenities_by_cat,
        images=images,
        seo_html=d.get("seoDescription"),
        description_html=d.get("description"),
        seousp_html=d.get("SEOUSP"),
        developer_experience_years=d.get("developerExperience") or d.get("developerYearOfExperience"),
        extras={
            "unitMinPageUrl": d.get("unitMinPageUrl"),
            "sizes_raw": d.get("sizes"),
            "unitMinBedroomCount": d.get("unitMinBedroomCount"),
            "highCost": d.get("highCost"),
            "lowCost": d.get("lowCost"),
            "currencySymbol": d.get("currency"),
            "statusId": d.get("statusId"),
            "categorytype": d.get("categorytype"),
            "projectArea_acres": d.get("projectArea"),
            "projectTag": d.get("projectTag"),
        }
    )


def build_no_repeat_phrases(p: ProjectNorm) -> List[str]:
    """
    Exact strings present on the PDP that we should avoid repeating verbatim in generated copy.
    Keep tight to control dedupe false positives.
    """
    phrases: List[str] = []
    for s in [p.project_name, p.city, p.locality, p.price_display,
              p.rera_id_primary, p.rera_id_project]:
        if s and isinstance(s, str) and s.strip():
            phrases.append(s.strip())

    # BHK strings and exact “sizes” phrase if present
    if p.bhk_list:
        phrases.extend(p.bhk_list)

    # Distances to well-known roads (often shown verbatim)
    for r in p.roads:
        if r.get("name") and r.get("distance"):
            phrases.append(f'{r["name"]} {r["distance"]} km')

    # Any obvious literals from extras that appear on PDP cards
    if p.extras.get("unitMinBedroomCount"):
        phrases.append(str(p.extras["unitMinBedroomCount"]))

    return sorted({x for x in phrases if x})