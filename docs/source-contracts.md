# Source contracts

Checked live on 23 November 2026 from this machine. A metadata page loading is not the same as a query. These were queried.

## Miami-Dade property points

- URL: `https://gisfs.miamidade.gov/mdarcgis/rest/services/MD_PA_PropertySearch/MapServer/0`
- Grain: one point per folio. A condominium unit is its own folio.
- Count that day: 944,376. Page size cap: 1,000.
- Fields used: `FOLIO` (string, 13), `TRUE_SITE_ADDR`, `CONDO_FLAG`, `PARENT_FOLIO`, point geometry.
- Request `outSR=4326`. The service's native reference is Florida State Plane (latest wkid 2236).

## Miami-Dade property polygons

- URL: same MapServer, layer 1.
- Count that day: 596,657.
- Fields used: `FOLIO`, `CONDOFLG`.
- Condo units often have no polygon. The parent folio polygon is the parcel, not the unit interior.

## Building footprints

- URL: `https://services.arcgis.com/8Pc9XBTAsYuxx9Ny/ArcGIS/rest/services/BuildingFootprintUBIDFolio_gdb/FeatureServer/0`
- Count that day: 605,762. Page cap: 2,000.
- Fields used: `UBID`, `FOLIO`, `PARENT_FOLIO`, `ADDRESS`, `CITY`, `MUNICIPAL_CODE`, `UNITS`, `FLOORS`, `YEAR_BUILT`, `BLDG_TYPE`.
- A folio can return more than one footprint. Do not collapse them into one building.
- `YEAR_BUILT` of 0 is treated as unpublished.

## Municipal boundaries

- URL: `https://services1.arcgis.com/1IKiqhM3CGiJICh6/ArcGIS/rest/services/MiamiDade_Municipalities_CITT/FeatureServer/0`
- 48 polygons. Fields used: `NAME`, `MUNICID`, `FIPSCODE`.
- City of Miami code is `01`. Coral Gables is `03`.
- Jurisdiction for a report comes from a point-in-polygon query against this layer. The local PostGIS copy is a backup for spatial checks. Some polygons failed to store; the live query is the one the report uses.

## City of Miami permits

- URL: `https://gis.miami.gov/gis/rest/services/Maps/AllCityPermits/MapServer/0`
- Count that day: 319,537. Page cap: 2,000.
- Fields used: `OBJECTID`, `PermitNumber`, `Folio`, `FULLADDR`, `PermitStatus`, `PermitType`, `ApplicationType`, `ApplicationStatus`, `ScopeOfWork`, `PermitStatusDate`.
- Status values include Active, Final, Issued, Expired, Pending, Hold, Cancelled, Revoked, InAdjustment. Some values have trailing spaces. They are stored as published.
- Records with a blank `PermitNumber` are rejected and not shown as findings.
- This layer is City of Miami only. It is not queried for any other municipality.
- An issued or active permit is not proof the work is finished. No rows is not proof of no work.

## FEMA flood zones, county copy

- URL: `https://services5.arcgis.com/wI5GZmCtnUU8ueya/ArcGIS/rest/services/Miami_Dade_County_FEMA_Flood_Zones/FeatureServer/8`
- Layer name: `FEMAFloodZone`. Fields: `FZONE`, `ZONESUBTY`, `ELEV`. No map effective date field.
- The report queries this layer at the property point and does not store the zone polygon. Zone polygons are large, and a point-in-polygon hit is what the finding claims.
- `ELEV` of -9999 is a sentinel. It is stored as unknown, not as an elevation. The field metadata retrieved that day did not state a unit, so a real elevation is quoted as the field value only.
- `hazards.fema.gov` reset the connection from this machine that day. It is not called at runtime.

## Not ingested

City of Miami 311, code enforcement, Miami Beach permits, association financials, recorded liens. Coverage for those is `not_covered` or absent. Absence is not a clean result.
