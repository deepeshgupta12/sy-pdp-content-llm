from __future__ import annotations
from typing import Any, Optional
from pydantic import BaseModel, Field, ConfigDict

# Raw: accept whatever SY PDP JSON provides; we don't enforce strict schema here.
class ProjectRaw(BaseModel):
    model_config = ConfigDict(extra="allow")  # keep unknown keys

# Normalized: fields we want available to the generator (safe to reference/summarize)
class ProjectNorm(BaseModel):
    project_id: str = Field(..., description="Stable SY project id/slug")
    project_name: str
    developer_name: Optional[str] = None
    city: Optional[str] = None
    micromarket: Optional[str] = None
    locality: Optional[str] = None
    rera_id: Optional[str] = None
    project_status: Optional[str] = Field(
        default=None,
        description="New Launch | Under Construction | Ready to Move | Completed | Unknown"
    )
    possession_date_iso: Optional[str] = Field(
        default=None, description="YYYY-MM or YYYY if available"
    )
    price_display: Optional[str] = None  # e.g., "₹1.2–1.8 Cr"
    price_min: Optional[float] = None
    price_max: Optional[float] = None
    currency: Optional[str] = "INR"
    bhk_list: Optional[list[str]] = None     # e.g., ["2 BHK","3 BHK"]
    unit_sizes_sqft: Optional[list[int]] = None
    amenities: Optional[list[str]] = None
    address_full: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    project_url: Optional[str] = None
    usp_tags: Optional[list[str]] = None
    # Anything else we may want to echo to the model as "context but not to be repeated verbatim"
    extras: dict[str, Any] = Field(default_factory=dict)