"""Read-only metadata endpoints for the static-analysis pattern catalog."""

from __future__ import annotations

from fastapi import APIRouter

from hackathon_reviewer.stages.static_analysis import (
    PATTERN_BUNDLES,
    PATTERN_PRESETS,
)

router = APIRouter(prefix="/api/static-analysis", tags=["static-analysis"])


@router.get("/bundles")
def list_bundles():
    """List available pattern bundles and starter-combo presets.

    The frontend uses this to render a checkbox list of bundles and a
    preset dropdown that pre-fills selections. Bundle ids and preset ids
    are stable across versions; safe to persist in saved configs.
    """
    bundles = [
        {
            "id": bid,
            "label": b["label"],
            "description": b["description"],
            "pattern_count": len(b["patterns"]),
        }
        for bid, b in PATTERN_BUNDLES.items()
    ]
    presets = [
        {
            "id": pid,
            "label": p["label"],
            "description": p["description"],
            "bundles": list(p["bundles"]),
        }
        for pid, p in PATTERN_PRESETS.items()
    ]
    return {"bundles": bundles, "presets": presets}
