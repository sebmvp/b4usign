from __future__ import annotations

import re
from typing import Any


FOLIO_RE = re.compile(r"^\d{13}$")
PERMIT_NUMBER_RE = re.compile(r"^[A-Za-z0-9-]+$")


def require_folio(value: str | None) -> str:
    text = (value or "").strip()
    if not FOLIO_RE.fullmatch(text):
        raise ValueError(f"folio must be 13 digits, got {value!r}")
    return text


def clean_address_query(value: str) -> str:
    cleaned = re.sub(r"[^A-Z0-9 #/-]", "", value.upper())
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned) < 3:
        raise ValueError("Enter at least 3 characters.")
    if len(cleaned) > 80:
        cleaned = cleaned[:80]
    return cleaned


def street_stem(address: str | None) -> str:
    """Drop a trailing unit token so 495 BRICKELL AVE 401 shares a stem with the parent."""
    text = re.sub(r"\s+", " ", (address or "").upper()).strip()
    parts = text.split(" ")
    if len(parts) >= 4 and parts[-1].isdigit():
        return " ".join(parts[:-1])
    return text


def arcgis_geometry(geom: dict[str, Any] | None) -> dict[str, Any] | None:
    if not geom:
        return None
    if "x" in geom and "y" in geom:
        return {"type": "Point", "coordinates": [geom["x"], geom["y"]]}
    rings = geom.get("rings")
    if rings:
        return {"type": "Polygon", "coordinates": rings}
    return None


def point_of(geom: dict[str, Any] | None) -> tuple[float, float] | None:
    if not geom:
        return None
    if geom.get("type") == "Point":
        lon, lat = geom["coordinates"]
        return float(lon), float(lat)
    if geom.get("type") == "Polygon":
        ring = geom["coordinates"][0]
        xs = [p[0] for p in ring]
        ys = [p[1] for p in ring]
        return sum(xs) / len(xs), sum(ys) / len(ys)
    return None


def refused_address_matches(
    subject_folio: str,
    parent_folio: str | None,
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Same street is not a link. Sibling units of the same parent are not collisions."""
    refused = []
    seen: set[str] = set()
    for row in candidates:
        folio = row.get("folio")
        if not folio or folio in seen:
            continue
        if folio == subject_folio or (parent_folio and folio == parent_folio):
            continue
        if parent_folio and row.get("parent_folio") == parent_folio:
            continue
        seen.add(folio)
        refused.append(row)
    return refused
