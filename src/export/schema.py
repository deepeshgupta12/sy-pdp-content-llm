CONTENT_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "project_id": {"type": "string"},
        "aeo_summary": {
            "type": "string",
            "description": "40–60 word direct, specific answer that summarizes the project for AEO."
        },
        "combined_narrative": {"type": "string"},
        "sections": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "who_is_it_for": {"type": "string"},
                "location_connectivity": {"type": "string"},
                "unit_mix_floorplans": {"type": "string"},
                "amenities_lifestyle": {"type": "string"},
                "pricing_payment_notes": {"type": "string"},
                "construction_status_rera": {"type": "string"},
                "developer_profile_eeat": {"type": "string"},
                "nearby_alternatives": {"type": "string"},
                "faqs": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "q": {"type": "string"},
                            "a": {"type": "string"}
                        },
                        "required": ["q", "a"]
                    }
                }
            },
            "required": [
                "who_is_it_for",
                "location_connectivity",
                "unit_mix_floorplans",
                "amenities_lifestyle",
                "pricing_payment_notes",
                "construction_status_rera",
                "developer_profile_eeat",
                "nearby_alternatives",
                "faqs"
            ]
        },
        "schema_org": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "faqpage": {"type": "object"},
                "howto": {"type": "object"}
            }
        },
        "citations": {
            "type": "array",
            "items": {"type": "string"}
        }
    },
    "required": ["project_id", "aeo_summary", "combined_narrative", "sections"]
}