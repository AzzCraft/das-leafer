from __future__ import annotations


HFVI_PROFILE = "hfvi_canvas_webgl_game"
REQUIRED_ASSET_SECTION = "## 8. HFVI asset declarations"
REQUIRED_LAYOUT_SECTION = "## 9. Layout conformance rules"


def describe_hfvi_requirements() -> dict[str, object]:
    return {
        "interactionProfile": HFVI_PROFILE,
        "requiredAppendixSections": [
            REQUIRED_ASSET_SECTION,
            REQUIRED_LAYOUT_SECTION,
        ],
    }


def validate_hfvi_gate(master_doc_text: str) -> list[str]:
    """Return a list of missing HFVI sections from the master doc."""
    missing: list[str] = []
    for section in [REQUIRED_ASSET_SECTION, REQUIRED_LAYOUT_SECTION]:
        if section not in master_doc_text:
            missing.append(section)
    return missing
