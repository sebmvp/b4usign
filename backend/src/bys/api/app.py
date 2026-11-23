from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from ..ask import answer_question
from ..config import engineering_enabled
from ..db import connect, recover_orphans
from ..geo import require_folio
from ..pipeline import PropertyNotFound, resolve_property, search_live
from ..report import geometry_for, load_report
from ..sources import SOURCES


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        conn = connect()
        recover_orphans(conn)
        conn.commit()
        conn.close()
    except Exception:
        pass
    yield


app = FastAPI(title="Before You Sign", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class AskBody(BaseModel):
    question: str = Field(min_length=3, max_length=500)


def folio_from_id(property_id: str) -> str:
    return require_folio(property_id.removeprefix("mdc-folio-"))


@app.get("/api/v1/health")
def health() -> dict:
    try:
        conn = connect()
        row = conn.execute("SELECT postgis_version() AS version").fetchone()
        conn.close()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Database unavailable: {exc}") from exc
    return {"status": "ok", "postgis": row["version"]}


@app.get("/api/v1/sources")
def sources() -> dict:
    conn = connect()
    try:
        snapshots = conn.execute(
            """
            SELECT DISTINCT ON (source_id) source_id, retrieved_at, record_count
            FROM meta.source_snapshots
            ORDER BY source_id, retrieved_at DESC
            """
        ).fetchall()
    except Exception:
        snapshots = []
    finally:
        conn.close()
    seen = {row["source_id"]: row for row in snapshots}
    payload = []
    for source in SOURCES:
        snap = seen.get(source["source_id"])
        payload.append(
            {
                **source,
                "last_retrieved_at": snap["retrieved_at"].isoformat() if snap else None,
            }
        )
    return {"sources": payload}


@app.get("/api/v1/coverage")
def coverage() -> dict:
    return sources()


@app.get("/api/v1/properties/search")
def search(q: str = Query(min_length=3, max_length=80)) -> dict:
    try:
        results = search_live(q)
        return {"results": results, "source": "live"}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        local = _search_local(q)
        if local:
            return {"results": local, "source": "local", "live_error": str(exc)}
        raise HTTPException(status_code=503, detail=f"Address search failed: {exc}") from exc


@app.get("/api/v1/properties/{property_id}")
def property_detail(property_id: str) -> dict:
    report = _report(property_id, "buy", "condo", refresh=False)
    return report["property"]


@app.get("/api/v1/properties/{property_id}/report")
def property_report(
    property_id: str,
    intent: str = Query(default="buy"),
    use: str = Query(default="condo"),
    refresh: bool = False,
) -> dict:
    return _report(property_id, intent, use, refresh)


@app.get("/api/v1/evidence/{evidence_id}")
def evidence(evidence_id: str, property_id: str = Query(...)) -> dict:
    report = load_report(property_id, "buy", "condo")
    if not report:
        raise HTTPException(status_code=404, detail="Property is not loaded.")
    for finding in report["findings"]:
        if finding["id"] == evidence_id:
            return finding
    raise HTTPException(status_code=404, detail="Evidence is not on this property.")


@app.post("/api/v1/properties/{property_id}/ask")
def ask(property_id: str, body: AskBody, intent: str = "buy", use: str = "condo") -> dict:
    report = _report(property_id, intent, use, refresh=False)
    result = answer_question(body.question, report)
    result["property_id"] = property_id
    return result


@app.get("/api/v1/engineering")
def engineering() -> dict:
    if not engineering_enabled():
        raise HTTPException(status_code=404, detail="Not found.")
    conn = connect()
    try:
        runs = conn.execute(
            """
            SELECT run_id, source_id, status, started_at, finished_at,
                   rows_read, rows_loaded, rows_rejected, error_message, query_text
            FROM ops.ingest_runs
            ORDER BY started_at DESC
            LIMIT 20
            """
        ).fetchall()
        rejected = conn.execute(
            """
            SELECT source_id, record_key, reason_code, detail, created_at
            FROM ops.rejected_records
            ORDER BY created_at DESC
            LIMIT 20
            """
        ).fetchall()
        counts = conn.execute(
            """
            SELECT
              (SELECT count(*) FROM core.property_identities) AS properties,
              (SELECT count(*) FROM evidence.permits) AS permits,
              (SELECT count(*) FROM ops.rejected_records) AS rejected,
              (SELECT count(*) FROM evidence.permit_versions) AS permit_versions
            """
        ).fetchone()
    finally:
        conn.close()
    return {
        "runs": [_jsonable(row) for row in runs],
        "rejected": [_jsonable(row) for row in rejected],
        "counts": counts,
    }


def _report(property_id: str, intent: str, use: str, refresh: bool) -> dict:
    try:
        folio = folio_from_id(property_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    cached = _safe_load(property_id, intent, use)
    if cached and not refresh and _fresh(cached.get("retrieved_at")):
        return _with_geometry(cached)
    try:
        resolve_property(folio)
    except PropertyNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        if cached:
            cached["refresh_error"] = str(exc)
            return _with_geometry(cached)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    loaded = load_report(property_id, intent, use)
    if not loaded:
        raise HTTPException(status_code=500, detail="Resolve finished but the property was not stored.")
    return _with_geometry(loaded)


def _safe_load(property_id: str, intent: str, use: str) -> dict | None:
    try:
        return load_report(property_id, intent, use)
    except Exception:
        return None


def _with_geometry(report: dict) -> dict:
    geom = None
    try:
        geom = geometry_for(report["property"]["property_id"])
    except Exception:
        geom = None
    if geom:
        report["property"]["geometry"] = geom.get("geometry")
        report["property"]["geometry_kind"] = geom.get("geometry_kind")
    return report


def _fresh(value: str | None) -> bool:
    if not value:
        return False
    try:
        retrieved = datetime.fromisoformat(value)
    except ValueError:
        return False
    if retrieved.tzinfo is None:
        retrieved = retrieved.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - retrieved < timedelta(hours=12)


def _search_local(query: str) -> list[dict]:
    conn = connect()
    try:
        rows = conn.execute(
            """
            SELECT property_id, folio, site_address, condo_flag, parent_folio, lon, lat
            FROM core.property_identities
            WHERE site_address ILIKE %s
            ORDER BY site_address
            LIMIT 8
            """,
            (f"%{query.strip()}%",),
        ).fetchall()
    except Exception:
        return []
    finally:
        conn.close()
    return [
        {
            "property_id": row["property_id"],
            "folio": row["folio"],
            "address": row["site_address"],
            "condo_flag": row["condo_flag"],
            "parent_folio": row["parent_folio"],
            "lon": row["lon"],
            "lat": row["lat"],
        }
        for row in rows
    ]


def _jsonable(row: dict) -> dict:
    payload = {}
    for key, value in row.items():
        payload[key] = value.isoformat() if isinstance(value, datetime) else value
    return payload
