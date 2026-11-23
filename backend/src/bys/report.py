from __future__ import annotations

from datetime import datetime
from typing import Any

from .db import connect
from .records import folio_source_url, permit_source_url
from .sources import FLOOD, PA_POINTS

STATUS_LABELS = {
    "available": "Available",
    "available_with_limitations": "Available with limitations",
    "not_applicable": "Not applicable",
    "not_covered": "Not covered",
    "temporarily_unavailable": "Temporarily unavailable",
    "outdated": "Outdated",
    "match_unresolved": "Match unresolved",
    "checked_none": "Checked, no matching records",
}


def load_report(property_id: str, intent: str, use: str) -> dict[str, Any] | None:
    intent = "rent" if intent == "rent" else "buy"
    conn = connect()
    try:
        identity = conn.execute(
            "SELECT * FROM core.property_identities WHERE property_id = %s",
            (property_id,),
        ).fetchone()
        if not identity:
            return None
        folio = identity["folio"]
        parent = identity["parent_folio"]
        permits = conn.execute(
            """
            SELECT * FROM evidence.permits
            WHERE folio = %(folio)s OR folio = %(parent)s
            ORDER BY status_at DESC NULLS LAST, permit_number
            """,
            {"folio": folio, "parent": parent or ""},
        ).fetchall()
        flood = conn.execute(
            "SELECT * FROM evidence.flood_findings WHERE property_id = %s",
            (property_id,),
        ).fetchone()
        buildings = conn.execute(
            """
            SELECT * FROM core.buildings
            WHERE folio = %(folio)s OR folio = %(parent)s
            ORDER BY ubid
            """,
            {"folio": folio, "parent": parent or ""},
        ).fetchall()
        coverage = conn.execute(
            """
            SELECT source_id, status, detail, checked_at
            FROM ops.source_coverage WHERE property_id = %s ORDER BY source_id
            """,
            (property_id,),
        ).fetchall()
        reviews = conn.execute(
            """
            SELECT method, decision, reason, evidence
            FROM ops.match_reviews WHERE property_id = %s ORDER BY created_at DESC
            LIMIT 12
            """,
            (property_id,),
        ).fetchall()
    finally:
        conn.close()
    return assemble(identity, permits, flood, buildings, coverage, reviews, intent, use)


def assemble(
    identity: dict[str, Any],
    permits: list[dict[str, Any]],
    flood: dict[str, Any] | None,
    buildings: list[dict[str, Any]],
    coverage: list[dict[str, Any]],
    reviews: list[dict[str, Any]],
    intent: str,
    use: str,
) -> dict[str, Any]:
    official_use = "condo" if identity.get("condo_flag") == "Y" else "house"
    findings = []
    findings.append(_identity_finding(identity))
    if identity.get("jurisdiction_name"):
        findings.append(_jurisdiction_finding(identity))
    for review in reviews:
        if review.get("decision") == "refused":
            findings.append(_refusal_finding(identity, review))
    if buildings:
        findings.append(_building_finding(identity, buildings))
    else:
        findings.append(_no_building_finding(identity))
    unit_permits = [row for row in permits if row.get("folio") == identity.get("folio")]
    parent_permits = [
        row
        for row in permits
        if identity.get("parent_folio") and row.get("folio") == identity.get("parent_folio")
    ]
    for row in unit_permits:
        findings.append(_permit_finding(row, "unit_folio"))
    for row in parent_permits:
        findings.append(_permit_finding(row, "parent_folio"))
    if flood and flood.get("zone_code"):
        findings.append(_flood_finding(flood))
    elif flood is None:
        findings.append(_flood_missing_finding(identity))
    checklist = _checklist(intent, official_use, findings, coverage)
    return {
        "property": _property_payload(identity, official_use),
        "intent": intent,
        "requested_use": use if use in {"house", "condo"} else official_use,
        "official_use": official_use,
        "findings": findings,
        "coverage": [_coverage_payload(row) for row in coverage],
        "checklist": checklist,
        "buildings": [_building_payload(row) for row in buildings],
        "retrieved_at": _iso(identity.get("retrieved_at")),
    }


def _property_payload(identity: dict[str, Any], official_use: str) -> dict[str, Any]:
    return {
        "property_id": identity["property_id"],
        "address": identity.get("site_address"),
        "folio": identity.get("folio"),
        "parent_folio": identity.get("parent_folio"),
        "condo_flag": identity.get("condo_flag"),
        "official_use": official_use,
        "municipality": identity.get("jurisdiction_name"),
        "jurisdiction_id": identity.get("jurisdiction_id"),
        "match_status": identity.get("match_status"),
        "match_method": identity.get("match_method"),
        "lon": identity.get("lon"),
        "lat": identity.get("lat"),
        "geometry_kind": identity.get("geometry_kind"),
        "limitations": identity.get("limitations") or "",
        "source_url": folio_source_url(identity["folio"]),
    }


def _identity_finding(identity: dict[str, Any]) -> dict[str, Any]:
    use = "condominium unit" if identity.get("condo_flag") == "Y" else "property"
    parent = identity.get("parent_folio")
    what = (
        f"Miami-Dade folio {identity.get('folio')} is recorded at "
        f"{identity.get('site_address') or 'an unpublished address'}."
    )
    if parent:
        what += f" Parent folio is {parent}."
    return _finding(
        finding_id=f"identity:{identity['property_id']}",
        theme="Property identity",
        title=f"Official {use} record",
        what=what,
        why="The folio is the county identifier. A unit folio is not the building, and a shared street address is not the same parcel.",
        ask="Confirm the folio on the listing, the contract, and the county record before you rely on this report.",
        source_name="Miami-Dade Property Appraiser GIS",
        source_record_id=identity.get("folio"),
        source_url=folio_source_url(identity["folio"]),
        attribution="official_folio",
        fields={
            "FOLIO": identity.get("folio"),
            "TRUE_SITE_ADDR": identity.get("site_address"),
            "CONDO_FLAG": identity.get("condo_flag"),
            "PARENT_FOLIO": identity.get("parent_folio"),
            "match_method": identity.get("match_method"),
        },
        caveat=identity.get("limitations") or "",
    )


def _jurisdiction_finding(identity: dict[str, Any]) -> dict[str, Any]:
    return _finding(
        finding_id=f"jurisdiction:{identity['property_id']}",
        theme="Property identity",
        title=f"Governing municipality: {identity.get('jurisdiction_name')}",
        what=(
            f"The property point falls in {identity.get('jurisdiction_name')} "
            f"(municipal code {str(identity.get('jurisdiction_id') or '').removeprefix('mdc-muni-')})."
        ),
        why="Permit and code records are municipal. A county parcel record does not mean every city's database was searched.",
        ask="Ask which building department actually reviews work at this address.",
        source_name="Miami-Dade municipal boundaries",
        source_record_id=identity.get("jurisdiction_id"),
        source_url="https://services1.arcgis.com/1IKiqhM3CGiJICh6/ArcGIS/rest/services/MiamiDade_Municipalities_CITT/FeatureServer/0",
        attribution="boundary",
        fields={"municipality": identity.get("jurisdiction_name")},
    )


def _refusal_finding(identity: dict[str, Any], review: dict[str, Any]) -> dict[str, Any]:
    evidence = review.get("evidence") or {}
    if isinstance(evidence, str):
        evidence = {"note": evidence}
    other = evidence.get("folio")
    return _finding(
        finding_id=f"refused:{identity['property_id']}:{other}",
        theme="Property identity",
        title="Same street, different folio — not linked",
        what=(
            f"Folio {other} is also recorded near {evidence.get('address') or identity.get('site_address')}. "
            "It was not attached to this property."
        ),
        why="Address similarity alone is not an authoritative relationship. Attaching it could put another parcel's records on this report.",
        ask="If a listing uses only the street address, ask which folio it means.",
        source_name="Miami-Dade Property Appraiser GIS",
        source_record_id=other,
        source_url=folio_source_url(other) if other else PA_POINTS,
        attribution="refused_address_match",
        fields=evidence,
        caveat="Refused match. Not evidence about this folio.",
    )


def _building_finding(identity: dict[str, Any], buildings: list[dict[str, Any]]) -> dict[str, Any]:
    first = buildings[0]
    year = first.get("year_built")
    what = f"{len(buildings)} building footprint record(s) use this folio or its parent folio."
    if len(buildings) == 1 and first.get("bldg_type"):
        what = f"One footprint is linked. The layer describes it as {first.get('bldg_type')}."
        if year:
            what += f" Year built on that record: {year}."
    return _finding(
        finding_id=f"buildings:{identity['property_id']}",
        theme="Property identity",
        title="Building footprint link",
        what=what,
        why="A footprint is a mapped structure, not a condition report. More than one footprint is not automatically more than one building you should treat as confirmed.",
        ask="Ask which physical structure the folio refers to if more than one footprint is listed.",
        source_name="Miami-Dade building footprints",
        source_record_id=first.get("ubid"),
        source_url="https://services.arcgis.com/8Pc9XBTAsYuxx9Ny/ArcGIS/rest/services/BuildingFootprintUBIDFolio_gdb/FeatureServer/0",
        attribution="folio",
        fields={
            "count": len(buildings),
            "ubids": [row.get("ubid") for row in buildings],
            "types": [row.get("bldg_type") for row in buildings],
        },
    )


def _no_building_finding(identity: dict[str, Any]) -> dict[str, Any]:
    return _finding(
        finding_id=f"buildings-none:{identity['property_id']}",
        theme="Property identity",
        title="No linked building footprint",
        what="The building-footprint layer returned no footprint for this folio or its parent folio.",
        why="That does not mean there is no building. The footprint may be filed under a different folio.",
        ask="Ask for the building identification the association or seller uses, and compare it with the folio.",
        source_name="Miami-Dade building footprints",
        source_record_id=identity.get("folio"),
        source_url="https://services.arcgis.com/8Pc9XBTAsYuxx9Ny/ArcGIS/rest/services/BuildingFootprintUBIDFolio_gdb/FeatureServer/0",
        attribution="checked_none",
        status="checked_none",
    )


def _permit_finding(row: dict[str, Any], attribution: str) -> dict[str, Any]:
    status = row.get("permit_status") or "status not published"
    number = row.get("permit_number")
    scope = row.get("scope_of_work") or "scope not published"
    where = (
        "This record carries this unit folio."
        if attribution == "unit_folio"
        else "This record is on the parent parcel folio, not the unit folio."
    )
    return _finding(
        finding_id=f"permit:{row.get('source_object_id')}",
        theme="Permit history",
        title=f"{str(status).strip() or 'Permit'} · {number}",
        what=f"City of Miami permit {number} is recorded as \"{status}\". Type: {row.get('permit_type') or 'not published'}. Scope: {scope}. {where}",
        why=_permit_why(status),
        ask=f"Ask whether the work under {number} is finished, and request the inspection history. A parent-parcel permit may not be about your unit."
        if attribution == "parent_folio"
        else f"Ask whether the work under {number} is finished, and request the inspection history.",
        source_name="City of Miami All City Permits",
        source_record_id=number,
        source_url=row.get("source_url") or permit_source_url(number),
        event_date=_iso(row.get("status_at")),
        retrieved_at=_iso(row.get("retrieved_at")),
        attribution=attribution,
        fields={
            "PermitNumber": number,
            "PermitStatus": status,
            "PermitType": row.get("permit_type"),
            "ApplicationType": row.get("application_type"),
            "ScopeOfWork": row.get("scope_of_work"),
            "Folio": row.get("folio"),
            "FULLADDR": row.get("full_address"),
            "PermitStatusDate": _iso(row.get("status_at")),
        },
        caveat="Status is shown as published, including odd spacing when the source has it.",
    )


def _permit_why(status: str) -> str:
    folded = str(status or "").strip().lower()
    if folded == "final":
        return "Final is the city's recorded status. It is not your inspection, and it does not close other permits."
    if folded in {"issued", "active", "pending", "hold", "inadjustment"}:
        return "This status does not prove the work is finished."
    if folded in {"expired", "cancelled", "revoked"}:
        return "This is the city's recorded status. It does not describe the current condition of the building."
    return "The status is shown as published. It is not a safety or compliance judgment."


def _flood_finding(flood: dict[str, Any]) -> dict[str, Any]:
    zone = flood.get("zone_code")
    elev = flood.get("elevation")
    if isinstance(elev, (int, float)) and elev <= -999:
        elev = None
    elev_text = (
        f" The layer's ELEV field is {elev}. The field metadata we retrieved does not state the unit."
        if elev not in (None, "")
        else " No elevation value was published on this feature."
    )
    return _finding(
        finding_id=f"flood:{flood.get('property_id')}",
        theme="Flood hazard designation",
        title=f"FEMA zone {zone} at this point",
        what=f"The county-published FEMA flood layer places this property point in zone {zone}.{elev_text}",
        why=(
            "Zone X is the map code for an area outside the 1-percent-annual-chance floodplain on this layer. "
            "It is not a promise that the property will not flood, and it is not an elevation certificate."
            if str(zone).upper() == "X"
            else "A flood-zone designation is a regulatory map class. It is not a prediction that this property will flood, and it is not an elevation certificate."
        ),
        ask="Ask for an elevation certificate and whether a Letter of Map Change exists. This layer did not publish a map effective date.",
        source_name="Miami-Dade FEMA flood zones (FEMA, county copy)",
        source_record_id=flood.get("source_feature_id"),
        source_url=FLOOD + "?f=pjson",
        attribution="point_in_zone",
        fields={
            "FZONE": zone,
            "ZONESUBTY": flood.get("zone_subtype"),
            "ELEV": elev,
            "map_effective_date": None,
        },
        caveat=flood.get("limitations") or "No map effective date on this layer.",
        status="available_with_limitations",
    )


def _flood_missing_finding(identity: dict[str, Any]) -> dict[str, Any]:
    return _finding(
        finding_id=f"flood-none:{identity['property_id']}",
        theme="Flood hazard designation",
        title="No flood zone returned",
        what="The flood layer returned no zone at this property point.",
        why="That is not a determination of low risk. The service may have failed, or the point may fall outside a published polygon.",
        ask="Check the FEMA Flood Map Service Center before you treat flood insurance as settled.",
        source_name="Miami-Dade FEMA flood zones",
        source_record_id=identity.get("folio"),
        source_url=FLOOD,
        attribution="checked_none",
        status="checked_none",
    )


def _checklist(intent: str, official_use: str, findings: list[dict[str, Any]], coverage: list[dict[str, Any]]) -> list[dict[str, str]]:
    items = []
    unit = [row for row in findings if row.get("attribution") == "unit_folio"]
    parent = [row for row in findings if row.get("attribution") == "parent_folio"]
    if unit:
        numbers = ", ".join(str(row.get("source_record_id")) for row in unit[:4])
        items.append(
            {
                "id": "ask-unit-permits",
                "kind": "evidence",
                "text": f"Ask whether the work under {numbers} is finished, and request the inspection history. A recorded status is not your inspection.",
            }
        )
    if parent:
        items.append(
            {
                "id": "ask-parent-permits",
                "kind": "evidence",
                "text": f"{len(parent)} published permit records are on the parent parcel, not this unit. Ask which of them affect this unit.",
            }
        )
    for finding in findings:
        if finding["id"].startswith("flood:"):
            items.append(
                {
                    "id": f"ask-{finding['id']}",
                    "kind": "evidence",
                    "text": "Ask for an elevation certificate and any Letter of Map Change. The zone on this page is not a premium quote.",
                }
            )
        if finding["id"].startswith("refused:"):
            items.append(
                {
                    "id": f"ask-{finding['id']}",
                    "kind": "evidence",
                    "text": "Ask the listing which folio it means. Another folio on this street was not linked.",
                }
            )
    covered = {row.get("source_id"): row.get("status") for row in coverage}
    if covered.get("miami_permits") == "not_applicable":
        items.append(
            {
                "id": "general-other-city",
                "kind": "evidence",
                "text": "City of Miami permits were not searched. Ask the municipality named on this report for its permit record.",
            }
        )
    if covered.get("miami_permits") == "checked_none":
        items.append(
            {
                "id": "general-no-permits",
                "kind": "evidence",
                "text": "No City of Miami permit was published for this folio. Ask the seller for permit history anyway. No matching record is not a clean building.",
            }
        )
    items.append(
        {
            "id": "general-enforcement",
            "kind": "general",
            "text": "This report does not include code-enforcement cases. Ask the building department whether any cases are open.",
        }
    )
    if official_use == "condo" and intent == "buy":
        items.extend(
            [
                {
                    "id": "general-reserves",
                    "kind": "general",
                    "text": "Request the association budget, reserve study, and any special-assessment notices. Those documents are not in this report.",
                },
                {
                    "id": "general-estoppel",
                    "kind": "general",
                    "text": "Ask for the estoppel and a statement of unpaid assessments. County parcel data does not show association finances.",
                },
            ]
        )
    elif official_use == "condo" and intent == "rent":
        items.append(
            {
                "id": "general-rent-condo",
                "kind": "general",
                "text": "Ask the landlord which repairs are the association's and which are theirs. Parent-parcel permits may not be about your unit.",
            }
        )
    elif intent == "buy":
        items.append(
            {
                "id": "general-house-buy",
                "kind": "general",
                "text": "Request seller disclosures and any inspection you commission. This report is not an inspection.",
            }
        )
    else:
        items.append(
            {
                "id": "general-house-rent",
                "kind": "general",
                "text": "Ask what the landlord will repair before move-in, in writing. A permit record is not a promise about the unit's condition.",
            }
        )
    items.append(
        {
            "id": "general-flood-insurance",
            "kind": "general",
            "text": "Ask an insurer what flood coverage would cost. The map zone is not a quote and not a forecast.",
        }
    )
    return items


def _finding(**kwargs: Any) -> dict[str, Any]:
    if "finding_id" in kwargs:
        kwargs["id"] = kwargs.pop("finding_id")
    kwargs.setdefault("status", "available")
    kwargs.setdefault("event_date", None)
    kwargs.setdefault("retrieved_at", None)
    kwargs.setdefault("caveat", "")
    kwargs.setdefault("fields", {})
    return kwargs


def _coverage_payload(row: dict[str, Any]) -> dict[str, Any]:
    status = row.get("status")
    return {
        "source_id": row.get("source_id"),
        "status": status,
        "label": STATUS_LABELS.get(status, status),
        "detail": row.get("detail"),
        "checked_at": _iso(row.get("checked_at")),
    }


def _building_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "ubid": row.get("ubid"),
        "folio": row.get("folio"),
        "address": row.get("address"),
        "city": row.get("city"),
        "year_built": row.get("year_built"),
        "units": row.get("units") or None,
        "floors": row.get("floors") or None,
        "bldg_type": row.get("bldg_type"),
    }


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def geometry_for(property_id: str) -> dict[str, Any] | None:
    conn = connect()
    try:
        row = conn.execute(
            """
            SELECT geometry_kind,
                   ST_AsGeoJSON(geom)::json AS geom,
                   lon, lat
            FROM core.property_identities
            WHERE property_id = %s
            """,
            (property_id,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    return {
        "geometry_kind": row["geometry_kind"],
        "geometry": row["geom"],
        "lon": row["lon"],
        "lat": row["lat"],
    }
