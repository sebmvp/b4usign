"""Verified source contracts. Status here is what this app actually queries."""

from __future__ import annotations

PA_POINTS = "https://gisfs.miamidade.gov/mdarcgis/rest/services/MD_PA_PropertySearch/MapServer/0"
PA_POLYGONS = "https://gisfs.miamidade.gov/mdarcgis/rest/services/MD_PA_PropertySearch/MapServer/1"
BUILDINGS = (
    "https://services.arcgis.com/8Pc9XBTAsYuxx9Ny/ArcGIS/rest/services/"
    "BuildingFootprintUBIDFolio_gdb/FeatureServer/0"
)
MUNICIPALITIES = (
    "https://services1.arcgis.com/1IKiqhM3CGiJICh6/ArcGIS/rest/services/"
    "MiamiDade_Municipalities_CITT/FeatureServer/0"
)
PERMITS = "https://gis.miami.gov/gis/rest/services/Maps/AllCityPermits/MapServer/0"
FLOOD = (
    "https://services5.arcgis.com/wI5GZmCtnUU8ueya/ArcGIS/rest/services/"
    "Miami_Dade_County_FEMA_Flood_Zones/FeatureServer/8"
)

CITY_OF_MIAMI_CODE = "01"

SOURCES = [
    {
        "source_id": "mdc_property_points",
        "publisher": "Miami-Dade County Property Appraiser / GIS",
        "title": "Property Search points",
        "layer_url": PA_POINTS,
        "coverage_note": (
            "Countywide parcel points. Folio is a 13-digit string. "
            "A condominium unit folio is not a physical building."
        ),
        "record_grain": "parcel or condominium unit point",
        "status": "working",
    },
    {
        "source_id": "mdc_property_polygons",
        "publisher": "Miami-Dade County Property Appraiser / GIS",
        "title": "Property Search polygons",
        "layer_url": PA_POLYGONS,
        "coverage_note": (
            "Parcel polygons. Condo units often have no polygon of their own. "
            "The parent folio polygon is the parcel, not the unit interior."
        ),
        "record_grain": "parcel polygon",
        "status": "working",
    },
    {
        "source_id": "mdc_buildings",
        "publisher": "Miami-Dade County GIS",
        "title": "Building footprints with UBID and folio",
        "layer_url": BUILDINGS,
        "coverage_note": (
            "Physical building polygons. A folio can match more than one footprint. "
            "A shared street address is not a reason to attach a footprint."
        ),
        "record_grain": "building footprint",
        "status": "working",
    },
    {
        "source_id": "mdc_municipalities",
        "publisher": "Miami-Dade County GIS",
        "title": "Municipal boundaries",
        "layer_url": MUNICIPALITIES,
        "coverage_note": "Used to decide which city's permit records apply. 48 polygons.",
        "record_grain": "municipality polygon",
        "status": "working",
    },
    {
        "source_id": "miami_permits",
        "publisher": "City of Miami GIS",
        "title": "All City Permits",
        "layer_url": PERMITS,
        "coverage_note": (
            "City of Miami only. Not searched for other municipalities. "
            "An issued permit is not proof the work is finished. "
            "No matching record is not a clean building."
        ),
        "record_grain": "permit or application point",
        "status": "working",
    },
    {
        "source_id": "mdc_fema_flood",
        "publisher": "FEMA, redistributed by Miami-Dade County",
        "title": "FEMA flood hazard zones",
        "layer_url": FLOOD,
        "coverage_note": (
            "County copy of FEMA flood-hazard polygons. Zone is a map designation, "
            "not a prediction that this property will flood. This layer has no map "
            "effective date. The national NFHL host was unreachable from this machine "
            "on 23 November 2026, so that host is not a live dependency."
        ),
        "record_grain": "flood zone polygon, sampled at the property point",
        "status": "available_with_limitations",
    },
    {
        "source_id": "miami_311",
        "publisher": "City of Miami",
        "title": "311 service requests",
        "layer_url": (
            "https://services1.arcgis.com/CvuPhqcTQpZPT9qY/arcgis/rest/services/"
            "City_of_Miami_311_Service_Requests_Since_2015/FeatureServer/0"
        ),
        "coverage_note": "Not ingested. A nearby request would not prove a defect here.",
        "record_grain": "service request",
        "status": "not_covered",
    },
    {
        "source_id": "code_enforcement",
        "publisher": "Municipal building departments",
        "title": "Code enforcement and violations",
        "layer_url": "",
        "coverage_note": "Not ingested. Missing enforcement records are not a clean result.",
        "record_grain": "case",
        "status": "not_covered",
    },
]

# Folios confirmed against the live Property Appraiser point layer on 23 November 2026.
GOLD_SET = [
    {
        "folio": "0141381500010",
        "label": "495 Brickell Ave 401",
        "use": "condo",
        "role": "City of Miami condominium unit with permit records on the unit folio.",
    },
    {
        "folio": "0141210131000",
        "label": "3598 Avocado Ave",
        "use": "house",
        "role": "City of Miami house with a city permit on its folio.",
    },
    {
        "folio": "0341080770010",
        "label": "1 Alhambra Cir 201",
        "use": "condo",
        "role": "Coral Gables condominium unit. City of Miami permits do not apply.",
    },
]
