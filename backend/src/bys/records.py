from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from .config import DATA_ROOT
from .geo import arcgis_geometry, point_of
from .hashing import content_hash


def arcgis_time(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
    return None


def property_id_for(folio: str) -> str:
    return f"mdc-folio-{folio}"


def permit_source_url(permit_number: str) -> str:
    return (
        "https://gis.miami.gov/gis/rest/services/Maps/AllCityPermits/MapServer/0/query"
        f"?where=PermitNumber%3D%27{permit_number}%27&outFields=*&f=html"
    )


def folio_source_url(folio: str) -> str:
    return (
        "https://gisfs.miamidade.gov/mdarcgis/rest/services/MD_PA_PropertySearch/MapServer/0/query"
        f"?where=FOLIO%3D%27{folio}%27&outFields=*&f=html"
    )


def feature_attrs(feature: dict[str, Any]) -> dict[str, Any]:
    return feature.get("attributes") or {}


def parcel_from_feature(feature: dict[str, Any], *, polygon_flag: str | None = None) -> dict[str, Any]:
    attrs = feature_attrs(feature)
    geojson = arcgis_geometry(feature.get("geometry"))
    lon = lat = None
    if geojson and geojson["type"] == "Point":
        lon, lat = geojson["coordinates"]
    elif geojson:
        lon, lat = point_of(geojson) or (None, None)
    payload = {
        "folio": attrs.get("FOLIO"),
        "parent_folio": attrs.get("PARENT_FOLIO"),
        "condo_flag": attrs.get("CONDO_FLAG") or attrs.get("CONDOFLG"),
        "site_address": attrs.get("TRUE_SITE_ADDR"),
        "polygon_flag": polygon_flag,
        "lon": lon,
        "lat": lat,
        "source_object_id": str(attrs.get("OBJECTID") or attrs.get("PID") or ""),
        "attributes": attrs,
    }
    payload["content_hash"] = content_hash(payload["attributes"])
    payload["geojson"] = geojson
    return payload


def building_from_feature(feature: dict[str, Any]) -> dict[str, Any]:
    attrs = feature_attrs(feature)
    geojson = arcgis_geometry(feature.get("geometry"))
    year = attrs.get("YEAR_BUILT")
    payload = {
        "ubid": attrs.get("UBID"),
        "folio": attrs.get("FOLIO"),
        "parent_folio": attrs.get("PARENT_FOLIO"),
        "address": attrs.get("ADDRESS"),
        "city": attrs.get("CITY"),
        "municipal_code": (attrs.get("MUNICIPAL_CODE") or "").strip() or None,
        "units": attrs.get("UNITS"),
        "floors": attrs.get("FLOORS"),
        "year_built": year if year not in (0, "0") else None,
        "bldg_type": attrs.get("BLDG_TYPE"),
        "attributes": attrs,
    }
    payload["content_hash"] = content_hash(payload["attributes"])
    payload["geojson"] = geojson
    return payload


def permit_from_feature(feature: dict[str, Any]) -> dict[str, Any]:
    attrs = feature_attrs(feature)
    number = attrs.get("PermitNumber")
    if isinstance(number, str):
        number = number.strip() or None
    else:
        number = None
    folio = (attrs.get("Folio") or "").strip()
    return {
        "source_object_id": str(attrs.get("OBJECTID") or ""),
        "permit_number": number,
        "folio": folio,
        "full_address": attrs.get("FULLADDR"),
        "permit_status": attrs.get("PermitStatus"),
        "permit_type": attrs.get("PermitType"),
        "application_type": attrs.get("ApplicationType"),
        "application_status": attrs.get("ApplicationStatus"),
        "scope_of_work": attrs.get("ScopeOfWork"),
        "status_at": arcgis_time(attrs.get("PermitStatusDate")),
        "source_url": permit_source_url(number) if number else None,
        "content_hash": content_hash(attrs),
        "raw_json": json.dumps(attrs, default=str),
    }
