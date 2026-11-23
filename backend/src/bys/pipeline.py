"""Fetch one property from official services and publish it.

The county point layer has about 944,000 records. This path pages, but it
only pulls the folio a person opened, plus that folio's parent, buildings,
and City of Miami permits when the municipality is City of Miami.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from psycopg.types.json import Jsonb

from .arcgis import ArcGISClient, ArcGISError
from .bronze import utcnow, write_bronze, write_jsonl
from .config import DATA_ROOT
from .db import (
    connect,
    finish_run,
    new_id,
    quarantine,
    record_snapshot,
    set_coverage,
    start_run,
    upsert_sources,
)
from .geo import (
    clean_address_query,
    point_of,
    refused_address_matches,
    require_folio,
    street_stem,
)
from .records import (
    building_from_feature,
    feature_attrs,
    parcel_from_feature,
    permit_from_feature,
    property_id_for,
)
from .silver import read_parquet, split_permits
from .sources import (
    BUILDINGS,
    CITY_OF_MIAMI_CODE,
    FLOOD,
    MUNICIPALITIES,
    PA_POINTS,
    PA_POLYGONS,
    PERMITS,
    SOURCES,
)

log = logging.getLogger("bys")

PERMIT_FIELDS = (
    "OBJECTID,PermitNumber,Folio,FULLADDR,PermitStatus,PermitType,"
    "ApplicationType,ApplicationStatus,ScopeOfWork,PermitStatusDate"
)
BUILDING_FIELDS = (
    "OBJECTID,UBID,FOLIO,PARENT_FOLIO,ADDRESS,CITY,MUNICIPAL_CODE,"
    "UNITS,FLOORS,YEAR_BUILT,BLDG_TYPE"
)


class PropertyNotFound(LookupError):
    pass


def search_live(query: str) -> list[dict[str, Any]]:
    cleaned = clean_address_query(query)
    where = f"TRUE_SITE_ADDR LIKE '{cleaned.replace(chr(39), chr(39) * 2)}%'"
    client = ArcGISClient()
    try:
        page = client.query(
            PA_POINTS,
            {
                "where": where,
                "outFields": "FOLIO,TRUE_SITE_ADDR,CONDO_FLAG,PARENT_FOLIO",
                "returnGeometry": "true",
                "outSR": "4326",
                "resultRecordCount": 8,
            },
        )
    finally:
        client.close()
    hits = []
    for feature in page.get("features") or []:
        attrs = feature_attrs(feature)
        folio = attrs.get("FOLIO")
        if not folio:
            continue
        point = feature.get("geometry") or {}
        hits.append(
            {
                "property_id": property_id_for(folio),
                "folio": folio,
                "address": attrs.get("TRUE_SITE_ADDR"),
                "condo_flag": attrs.get("CONDO_FLAG"),
                "parent_folio": attrs.get("PARENT_FOLIO"),
                "lon": point.get("x"),
                "lat": point.get("y"),
            }
        )
    return hits


def resolve_property(folio: str) -> str:
    folio = require_folio(folio)
    client = ArcGISClient()
    try:
        return _resolve(client, folio)
    finally:
        client.close()


def _resolve(client: ArcGISClient, folio: str) -> str:
    point_features = client.pages(
        PA_POINTS,
        f"FOLIO = '{folio}'",
        "OBJECTID,FOLIO,TRUE_SITE_ADDR,CONDO_FLAG,PARENT_FOLIO",
        page_size=5,
    )
    if not point_features:
        raise PropertyNotFound(f"No Miami-Dade property point for folio {folio}.")
    subject = parcel_from_feature(point_features[0])
    parent_folio = subject.get("parent_folio")
    if parent_folio:
        try:
            parent_folio = require_folio(parent_folio)
        except ValueError:
            parent_folio = None
    subject["parent_folio"] = parent_folio

    parent = None
    if parent_folio:
        parent_features = client.pages(
            PA_POINTS,
            f"FOLIO = '{parent_folio}'",
            "OBJECTID,FOLIO,TRUE_SITE_ADDR,CONDO_FLAG,PARENT_FOLIO",
            page_size=5,
        )
        if parent_features:
            parent = parcel_from_feature(parent_features[0])

    polygon = _first_polygon(client, folio)
    parent_polygon = _first_polygon(client, parent_folio) if parent_folio else None
    if polygon:
        subject = _attach_polygon(subject, polygon)
    elif parent_polygon and parent:
        parent = _attach_polygon(parent, parent_polygon)

    folios = [folio] + ([parent_folio] if parent_folio else [])
    folio_where = " OR ".join(f"FOLIO = '{item}'" for item in folios)
    building_features = client.pages(
        BUILDINGS,
        folio_where,
        BUILDING_FIELDS,
        page_size=50,
    )
    buildings = [building_from_feature(feature) for feature in building_features]
    buildings = [row for row in buildings if row.get("ubid")]

    lon, lat = subject.get("lon"), subject.get("lat")
    if (lon is None or lat is None) and parent:
        lon, lat = parent.get("lon"), parent.get("lat")
    jurisdiction = _jurisdiction(client, lon, lat) if lon is not None else None

    permits_raw: list[dict[str, Any]] = []
    permit_error = None
    city_code = (jurisdiction or {}).get("source_code")
    if city_code == CITY_OF_MIAMI_CODE:
        try:
            for item in folios:
                permits_raw.extend(
                    client.pages(PERMITS, f"Folio = '{item}'", PERMIT_FIELDS, page_size=500)
                )
        except ArcGISError as exc:
            permit_error = str(exc)
    flood_raw = None
    flood_error = None
    if lon is not None:
        try:
            flood_raw = _flood(client, lon, lat)
        except ArcGISError as exc:
            flood_error = str(exc)

    stem = street_stem((parent or subject).get("site_address") or subject.get("site_address"))
    collisions = _address_candidates(client, stem)
    refused = refused_address_matches(folio, parent_folio, collisions)

    property_id = property_id_for(folio)
    run_id = new_id()
    bronze_dir, bronze_hash = write_bronze(
        "property_resolve",
        run_id,
        [
            {"query": folio, "points": point_features, "parent": parent_features if parent_folio else []},
            {"buildings": building_features},
            {"permits": permits_raw},
            {"flood": flood_raw},
        ],
        folio,
    )
    permit_rows = [permit_from_feature(feature) for feature in permits_raw]
    silver_dir = DATA_ROOT / "silver" / "miami_permits" / run_id
    jsonl_path = silver_dir / "permits.jsonl"
    write_jsonl(jsonl_path, permit_rows)
    silver_stats = split_permits(
        jsonl_path,
        silver_dir / "valid.parquet",
        silver_dir / "rejected.parquet",
    )
    valid_permits = read_parquet(silver_dir / "valid.parquet")
    rejected_permits = read_parquet(silver_dir / "rejected.parquet")

    geometry_kind = "point_only"
    geom = subject.get("geojson")
    if subject.get("geojson") and subject["geojson"]["type"] != "Point":
        geometry_kind = "parcel"
    elif parent and parent.get("geojson") and parent["geojson"]["type"] != "Point":
        geometry_kind = "parent_parcel"
        geom = parent["geojson"]

    limitations = _limitations(
        subject, parent, jurisdiction, buildings, refused, geometry_kind, silver_stats
    )
    conn = connect()
    try:
        with conn.transaction():
            upsert_sources(conn, SOURCES)
        _ensure_municipalities(conn, client)
        db_run = start_run(conn, "property_resolve", folio)
        try:
            with conn.transaction():
                _publish(
                    conn,
                    db_run,
                    property_id,
                    subject,
                    parent,
                    buildings,
                    jurisdiction,
                    valid_permits,
                    rejected_permits,
                    flood_raw,
                    flood_error,
                    permit_error,
                    refused,
                    geometry_kind,
                    geom,
                    limitations,
                    silver_stats,
                    bronze_dir,
                    bronze_hash,
                )
                conn.execute(
                    """
                    UPDATE ops.ingest_runs
                    SET status = 'succeeded', finished_at = %s,
                        rows_read = %s, rows_loaded = %s, rows_rejected = %s
                    WHERE run_id = %s
                    """,
                    (
                        utcnow(),
                        silver_stats["read"] + len(buildings) + 1,
                        silver_stats["valid"] + len(buildings) + 1,
                        silver_stats["rejected"],
                        db_run,
                    ),
                )
        except Exception as exc:
            finish_run(conn, db_run, status="failed", error=str(exc)[:2000])
            raise
        conn.commit()
    finally:
        conn.close()
    return property_id


def _first_polygon(client: ArcGISClient, folio: str | None) -> dict[str, Any] | None:
    if not folio:
        return None
    features = client.pages(
        PA_POLYGONS,
        f"FOLIO = '{folio}'",
        "OBJECTID,FOLIO,CONDOFLG,PID",
        page_size=2,
    )
    return features[0] if features else None


def _attach_polygon(row: dict[str, Any], feature: dict[str, Any]) -> dict[str, Any]:
    attrs = feature_attrs(feature)
    geojson = parcel_from_feature(feature, polygon_flag=attrs.get("CONDOFLG")).get("geojson")
    if geojson and geojson["type"] != "Point":
        row["geojson"] = geojson
        row["polygon_flag"] = attrs.get("CONDOFLG")
    return row


def _jurisdiction(client: ArcGISClient, lon: float, lat: float) -> dict[str, str] | None:
    geom = json.dumps({"x": lon, "y": lat, "spatialReference": {"wkid": 4326}})
    page = client.query(
        MUNICIPALITIES,
        {
            "geometry": geom,
            "geometryType": "esriGeometryPoint",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "NAME,MUNICID,FIPSCODE",
            "returnGeometry": "false",
        },
    )
    features = page.get("features") or []
    if not features:
        return None
    attrs = feature_attrs(features[0])
    code = str(attrs.get("MUNICID") or "").strip()
    return {
        "jurisdiction_id": f"mdc-muni-{code}",
        "name": attrs.get("NAME") or "Unknown",
        "source_code": code,
    }


def _flood(client: ArcGISClient, lon: float, lat: float) -> dict[str, Any] | None:
    geom = json.dumps({"x": lon, "y": lat, "spatialReference": {"wkid": 4326}})
    page = client.query(
        FLOOD,
        {
            "geometry": geom,
            "geometryType": "esriGeometryPoint",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "FID,FZONE,ZONESUBTY,ELEV,GlobalID",
            "returnGeometry": "false",
            "resultRecordCount": 1,
        },
    )
    features = page.get("features") or []
    if not features:
        return None
    attrs = feature_attrs(features[0])
    elev = attrs.get("ELEV")
    if isinstance(elev, (int, float)) and elev <= -999:
        elev = None
    return {
        "zone_code": (attrs.get("FZONE") or "").strip() or None,
        "zone_subtype": (attrs.get("ZONESUBTY") or "").strip() or None,
        "elevation": elev,
        "source_feature_id": str(attrs.get("FID") or attrs.get("GlobalID") or ""),
        "queried_lon": lon,
        "queried_lat": lat,
        "attributes": attrs,
    }


def _address_candidates(client: ArcGISClient, stem: str) -> list[dict[str, Any]]:
    if len(stem) < 3:
        return []
    where = f"TRUE_SITE_ADDR LIKE '{stem.replace(chr(39), chr(39) * 2)}%'"
    page = client.query(
        PA_POINTS,
        {
            "where": where,
            "outFields": "FOLIO,TRUE_SITE_ADDR,CONDO_FLAG,PARENT_FOLIO",
            "returnGeometry": "false",
            "resultRecordCount": 30,
        },
    )
    rows = []
    for feature in page.get("features") or []:
        attrs = feature_attrs(feature)
        rows.append(
            {
                "folio": attrs.get("FOLIO"),
                "address": attrs.get("TRUE_SITE_ADDR"),
                "condo_flag": attrs.get("CONDO_FLAG"),
                "parent_folio": attrs.get("PARENT_FOLIO"),
            }
        )
    return rows


def _limitations(subject, parent, jurisdiction, buildings, refused, geometry_kind, silver_stats) -> str:
    notes = []
    if subject.get("condo_flag") == "Y":
        notes.append(
            "This folio is a condominium unit record. It is not the physical building."
        )
    if geometry_kind == "parent_parcel":
        notes.append("The map outline is the parent parcel, not the inside of the unit.")
    elif geometry_kind == "point_only":
        notes.append("Only a property-appraiser point was found. That point is not a surveyed building outline.")
    if len(buildings) > 1:
        notes.append(
            f"The building-footprint layer returned {len(buildings)} footprints for the linked folios. "
            "They are listed separately and are not treated as one confirmed building."
        )
    if not buildings:
        notes.append("No building footprint was linked to this folio or its parent folio.")
    if refused:
        other = ", ".join(row["folio"] for row in refused[:4])
        notes.append(
            "Other official folios share this street address and were not linked: "
            f"{other}. Address similarity is not a match."
        )
    if not jurisdiction:
        notes.append("Municipality could not be determined from the boundary layer.")
    if silver_stats.get("rejected"):
        notes.append(
            f"{silver_stats['rejected']} permit records were missing a usable permit number or folio "
            "and were not published as findings."
        )
    return " ".join(notes)


def _ensure_municipalities(conn, client: ArcGISClient) -> None:
    row = conn.execute("SELECT count(*) AS n FROM core.jurisdictions").fetchone()
    if row and row["n"] >= 30:
        return
    features = client.pages(
        MUNICIPALITIES,
        "1=1",
        "FID,NAME,MUNICID,FIPSCODE",
        page_size=50,
        object_id_field="FID",
    )
    from .geo import arcgis_geometry
    from .hashing import content_hash

    with conn.transaction():
        for feature in features:
            attrs = feature_attrs(feature)
            code = str(attrs.get("MUNICID") or "").strip()
            if not code:
                continue
            geojson = arcgis_geometry(feature.get("geometry"))
            _insert_geom(
                conn,
                """
                INSERT INTO core.jurisdictions
                  (jurisdiction_id, source_code, name, fips, geom, content_hash, retrieved_at)
                VALUES (%s, %s, %s, %s, ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)), %s, %s)
                ON CONFLICT (jurisdiction_id) DO UPDATE SET
                  name = EXCLUDED.name,
                  geom = EXCLUDED.geom,
                  content_hash = EXCLUDED.content_hash,
                  retrieved_at = EXCLUDED.retrieved_at
                """,
                (
                    f"mdc-muni-{code}",
                    code,
                    attrs.get("NAME"),
                    str(attrs.get("FIPSCODE") or ""),
                    json.dumps(geojson) if geojson else None,
                    content_hash(attrs),
                    utcnow(),
                ),
                skip_geom=geojson is None,
            )
    conn.commit()


def _insert_geom(conn, sql: str, params: tuple, *, skip_geom: bool) -> None:
    if skip_geom:
        return
    try:
        with conn.transaction():
            conn.execute(sql, params)
    except Exception as exc:
        log.warning("geometry skipped: %s", exc)


def _publish(
    conn,
    run_id: str,
    property_id: str,
    subject: dict[str, Any],
    parent: dict[str, Any] | None,
    buildings: list[dict[str, Any]],
    jurisdiction: dict[str, str] | None,
    valid_permits: list[dict[str, Any]],
    rejected_permits: list[dict[str, Any]],
    flood: dict[str, Any] | None,
    flood_error: str | None,
    permit_error: str | None,
    refused: list[dict[str, Any]],
    geometry_kind: str,
    geom: dict[str, Any] | None,
    limitations: str,
    silver_stats: dict[str, int],
    bronze_dir,
    bronze_hash: str,
) -> None:
    now = utcnow()
    for parcel in filter(None, [subject, parent]):
        _upsert_parcel(conn, parcel, now)
    for building in buildings:
        _upsert_building(conn, building, now)
    identity_hash_payload = {
        "folio": subject["folio"],
        "parent": subject.get("parent_folio"),
        "address": subject.get("site_address"),
        "jurisdiction": (jurisdiction or {}).get("source_code"),
        "geometry_kind": geometry_kind,
        "limitations": limitations,
    }
    conn.execute(
        """
        INSERT INTO core.property_identities (
          property_id, folio, parent_folio, site_address, condo_flag,
          jurisdiction_id, jurisdiction_name, match_status, match_method,
          lon, lat, geom, geometry_kind, limitations, content_hash, retrieved_at
        ) VALUES (
          %s, %s, %s, %s, %s, %s, %s, 'resolved', 'official_folio',
          %s, %s, CASE WHEN %s::text IS NULL THEN NULL ELSE ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)) END,
          %s, %s, %s, %s
        )
        ON CONFLICT (property_id) DO UPDATE SET
          parent_folio = EXCLUDED.parent_folio,
          site_address = EXCLUDED.site_address,
          condo_flag = EXCLUDED.condo_flag,
          jurisdiction_id = EXCLUDED.jurisdiction_id,
          jurisdiction_name = EXCLUDED.jurisdiction_name,
          lon = EXCLUDED.lon,
          lat = EXCLUDED.lat,
          geom = EXCLUDED.geom,
          geometry_kind = EXCLUDED.geometry_kind,
          limitations = EXCLUDED.limitations,
          content_hash = EXCLUDED.content_hash,
          retrieved_at = EXCLUDED.retrieved_at
        """,
        (
            property_id,
            subject["folio"],
            subject.get("parent_folio"),
            subject.get("site_address"),
            subject.get("condo_flag"),
            (jurisdiction or {}).get("jurisdiction_id"),
            (jurisdiction or {}).get("name"),
            subject.get("lon"),
            subject.get("lat"),
            json.dumps(geom) if geom else None,
            json.dumps(geom) if geom else None,
            geometry_kind,
            limitations,
            __import__("bys.hashing", fromlist=["content_hash"]).content_hash(identity_hash_payload),
            now,
        ),
    )
    for row in valid_permits:
        _upsert_permit(conn, row, now)
    for row in rejected_permits:
        raw = row.get("raw_json")
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                raw = {"raw": raw}
        quarantine(
            conn,
            run_id=run_id,
            source_id="miami_permits",
            record_key=str(row.get("source_object_id") or ""),
            reason_code=str(row.get("reason_code") or "rejected"),
            detail="Record was not published as a finding.",
            raw=raw if isinstance(raw, dict) else {"raw": str(raw)},
        )
    if flood:
        from .hashing import content_hash

        conn.execute(
            """
            INSERT INTO evidence.flood_findings (
              property_id, zone_code, zone_subtype, elevation, source_feature_id,
              source_layer, source_url, queried_lon, queried_lat, map_effective_date,
              limitations, content_hash, retrieved_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NULL, %s, %s, %s)
            ON CONFLICT (property_id) DO UPDATE SET
              zone_code = EXCLUDED.zone_code,
              zone_subtype = EXCLUDED.zone_subtype,
              elevation = EXCLUDED.elevation,
              source_feature_id = EXCLUDED.source_feature_id,
              content_hash = EXCLUDED.content_hash,
              retrieved_at = EXCLUDED.retrieved_at
            """,
            (
                property_id,
                flood.get("zone_code"),
                flood.get("zone_subtype"),
                flood.get("elevation"),
                flood.get("source_feature_id"),
                "Miami-Dade FEMAFloodZone",
                FLOOD,
                flood.get("queried_lon"),
                flood.get("queried_lat"),
                "This county layer has no map effective date. A zone is not a prediction that the property will flood.",
                content_hash(flood.get("attributes") or flood),
                now,
            ),
        )
    for row in refused:
        conn.execute("DELETE FROM ops.match_reviews WHERE property_id = %s", (property_id,))
        break
    for row in refused:
        conn.execute(
            """
            INSERT INTO ops.match_reviews
              (review_id, property_id, method, decision, reason, evidence, created_at)
            VALUES (%s, %s, 'address_similarity', 'refused',
                    'Same street address is not an authoritative link.', %s, %s)
            """,
            (
                new_id(),
                property_id,
                Jsonb(row),
                now,
            ),
        )
    _coverage(
        conn,
        property_id,
        jurisdiction,
        silver_stats,
        permit_error,
        flood,
        flood_error,
        buildings,
        now,
    )
    record_snapshot(
        conn,
        source_id="property_resolve",
        run_id=run_id,
        query_text=subject["folio"],
        record_count=1 + len(buildings) + silver_stats["read"],
        content_hash=bronze_hash,
        bronze_path=str(bronze_dir),
    )


def _coverage(conn, property_id, jurisdiction, silver_stats, permit_error, flood, flood_error, buildings, now) -> None:
    set_coverage(
        conn,
        property_id,
        "mdc_property_points",
        "available",
        "Official folio returned by the property appraiser point layer.",
    )
    if not jurisdiction:
        set_coverage(
            conn,
            property_id,
            "miami_permits",
            "match_unresolved",
            "Municipality was not determined, so City of Miami permits were not searched.",
        )
    elif jurisdiction.get("source_code") != CITY_OF_MIAMI_CODE:
        set_coverage(
            conn,
            property_id,
            "miami_permits",
            "not_applicable",
            f"Property is in {jurisdiction.get('name')}. City of Miami permits were not searched. That is not a clean result.",
        )
    elif permit_error:
        set_coverage(
            conn,
            property_id,
            "miami_permits",
            "temporarily_unavailable",
            f"City of Miami permit service failed: {permit_error}",
        )
    elif silver_stats["valid"] == 0 and silver_stats["read"] == 0:
        set_coverage(
            conn,
            property_id,
            "miami_permits",
            "checked_none",
            "City of Miami permit search returned no records for this folio or its parent folio. That is not proof of no work.",
        )
    elif silver_stats["rejected"]:
        set_coverage(
            conn,
            property_id,
            "miami_permits",
            "available_with_limitations",
            f"Published {silver_stats['valid']} permit records. Held back {silver_stats['rejected']} without a usable permit number.",
        )
    else:
        set_coverage(
            conn,
            property_id,
            "miami_permits",
            "available",
            f"Published {silver_stats['valid']} City of Miami permit records.",
        )
    if buildings:
        status = "available_with_limitations" if len(buildings) > 1 else "available"
        set_coverage(
            conn,
            property_id,
            "mdc_buildings",
            status,
            f"{len(buildings)} footprint(s) linked by folio.",
        )
    else:
        set_coverage(
            conn,
            property_id,
            "mdc_buildings",
            "checked_none",
            "No building footprint linked to this folio or its parent folio.",
        )
    if flood_error:
        set_coverage(conn, property_id, "mdc_fema_flood", "temporarily_unavailable", flood_error)
    elif flood and flood.get("zone_code"):
        set_coverage(
            conn,
            property_id,
            "mdc_fema_flood",
            "available_with_limitations",
            f"Zone {flood['zone_code']} at the property point. No map effective date on this layer.",
        )
    else:
        set_coverage(
            conn,
            property_id,
            "mdc_fema_flood",
            "checked_none",
            "The flood layer returned no zone at this point. That is not a low-risk determination.",
        )
    set_coverage(
        conn,
        property_id,
        "code_enforcement",
        "not_covered",
        "Code enforcement is not in this report. Missing cases are not a clean result.",
    )
    set_coverage(
        conn,
        property_id,
        "miami_311",
        "not_covered",
        "311 requests are not in this report. A missing feed is not an absence of complaints.",
    )
    del now


def _upsert_parcel(conn, parcel: dict[str, Any], now) -> None:
    geojson = parcel.get("geojson")
    conn.execute(
        """
        INSERT INTO core.parcels (
          folio, parent_folio, condo_flag, site_address, polygon_flag,
          lon, lat, geom, source_object_id, content_hash, retrieved_at
        ) VALUES (
          %s, %s, %s, %s, %s, %s, %s,
          CASE WHEN %s::text IS NULL THEN NULL ELSE ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)) END,
          %s, %s, %s
        )
        ON CONFLICT (folio) DO UPDATE SET
          parent_folio = EXCLUDED.parent_folio,
          condo_flag = COALESCE(EXCLUDED.condo_flag, core.parcels.condo_flag),
          site_address = COALESCE(EXCLUDED.site_address, core.parcels.site_address),
          polygon_flag = COALESCE(EXCLUDED.polygon_flag, core.parcels.polygon_flag),
          lon = COALESCE(EXCLUDED.lon, core.parcels.lon),
          lat = COALESCE(EXCLUDED.lat, core.parcels.lat),
          geom = COALESCE(EXCLUDED.geom, core.parcels.geom),
          content_hash = EXCLUDED.content_hash,
          retrieved_at = EXCLUDED.retrieved_at
        """,
        (
            parcel["folio"],
            parcel.get("parent_folio"),
            parcel.get("condo_flag"),
            parcel.get("site_address"),
            parcel.get("polygon_flag"),
            parcel.get("lon"),
            parcel.get("lat"),
            json.dumps(geojson) if geojson else None,
            json.dumps(geojson) if geojson else None,
            parcel.get("source_object_id"),
            parcel["content_hash"],
            now,
        ),
    )


def _upsert_building(conn, building: dict[str, Any], now) -> None:
    geojson = building.get("geojson")
    conn.execute(
        """
        INSERT INTO core.buildings (
          ubid, folio, parent_folio, address, city, municipal_code,
          units, floors, year_built, bldg_type, geom, content_hash, retrieved_at
        ) VALUES (
          %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
          CASE WHEN %s::text IS NULL THEN NULL ELSE ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)) END,
          %s, %s
        )
        ON CONFLICT (ubid) DO UPDATE SET
          folio = EXCLUDED.folio,
          address = EXCLUDED.address,
          bldg_type = EXCLUDED.bldg_type,
          geom = EXCLUDED.geom,
          content_hash = EXCLUDED.content_hash,
          retrieved_at = EXCLUDED.retrieved_at
        """,
        (
            building["ubid"],
            building.get("folio"),
            building.get("parent_folio"),
            building.get("address"),
            building.get("city"),
            building.get("municipal_code"),
            building.get("units"),
            building.get("floors"),
            building.get("year_built"),
            building.get("bldg_type"),
            json.dumps(geojson) if geojson else None,
            json.dumps(geojson) if geojson else None,
            building["content_hash"],
            now,
        ),
    )


def _upsert_permit(conn, row: dict[str, Any], now) -> None:
    raw = row.get("raw_json")
    if not isinstance(raw, str):
        raw = json.dumps(raw, default=str)
    status_at = row.get("status_at")
    if hasattr(status_at, "isoformat"):
        status_at = status_at.isoformat()
    conn.execute(
        """
        INSERT INTO evidence.permit_versions (source_object_id, content_hash, observed_at, raw_json)
        VALUES (%s, %s, %s, %s::jsonb)
        ON CONFLICT DO NOTHING
        """,
        (str(row["source_object_id"]), row["content_hash"], now, raw),
    )
    conn.execute(
        """
        INSERT INTO evidence.permits (
          source_object_id, permit_number, folio, full_address, permit_status,
          permit_type, application_type, application_status, scope_of_work,
          status_at, source_url, content_hash, raw_json, retrieved_at
        ) VALUES (
          %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s
        )
        ON CONFLICT (source_object_id) DO UPDATE SET
          permit_number = EXCLUDED.permit_number,
          permit_status = EXCLUDED.permit_status,
          permit_type = EXCLUDED.permit_type,
          scope_of_work = EXCLUDED.scope_of_work,
          status_at = EXCLUDED.status_at,
          content_hash = EXCLUDED.content_hash,
          raw_json = EXCLUDED.raw_json,
          retrieved_at = EXCLUDED.retrieved_at
        """,
        (
            str(row["source_object_id"]),
            row.get("permit_number"),
            row.get("folio"),
            row.get("full_address"),
            row.get("permit_status"),
            row.get("permit_type"),
            row.get("application_type"),
            row.get("application_status"),
            row.get("scope_of_work"),
            status_at,
            row.get("source_url"),
            row.get("content_hash"),
            raw,
            now,
        ),
    )
