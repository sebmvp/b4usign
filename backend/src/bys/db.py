from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .config import database_url


def connect() -> psycopg.Connection:
    return psycopg.connect(database_url(), row_factory=dict_row)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return uuid4().hex


def recover_orphans(conn: psycopg.Connection) -> int:
    row = conn.execute(
        """
        UPDATE ops.ingest_runs
        SET status = 'failed',
            finished_at = COALESCE(finished_at, now()),
            error_message = COALESCE(error_message, 'orphaned: process interrupted before run completed')
        WHERE status = 'running'
        RETURNING run_id
        """
    ).fetchall()
    return len(row)


def upsert_sources(conn: psycopg.Connection, sources: list[dict[str, str]]) -> None:
    for source in sources:
        conn.execute(
            """
            INSERT INTO meta.source_registry
              (source_id, publisher, title, layer_url, coverage_note, record_grain, status)
            VALUES (%(source_id)s, %(publisher)s, %(title)s, %(layer_url)s, %(coverage_note)s, %(record_grain)s, %(status)s)
            ON CONFLICT (source_id) DO UPDATE SET
              publisher = EXCLUDED.publisher,
              title = EXCLUDED.title,
              layer_url = EXCLUDED.layer_url,
              coverage_note = EXCLUDED.coverage_note,
              record_grain = EXCLUDED.record_grain,
              status = EXCLUDED.status
            """,
            source,
        )


def record_snapshot(
    conn: psycopg.Connection,
    *,
    source_id: str,
    run_id: str,
    query_text: str,
    record_count: int,
    content_hash: str,
    bronze_path: str,
    source_edited_at: datetime | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO meta.source_snapshots
          (snapshot_id, source_id, run_id, retrieved_at, query_text, record_count, content_hash, bronze_path, source_edited_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            new_id(),
            source_id,
            run_id,
            utcnow(),
            query_text,
            record_count,
            content_hash,
            bronze_path,
            source_edited_at,
        ),
    )


def start_run(conn: psycopg.Connection, source_id: str, query_text: str) -> str:
    run_id = new_id()
    with conn.transaction():
        conn.execute(
            """
            INSERT INTO ops.ingest_runs
              (run_id, source_id, status, started_at, query_text)
            VALUES (%s, %s, 'running', %s, %s)
            """,
            (run_id, source_id, utcnow(), query_text),
        )
    return run_id


def finish_run(
    conn: psycopg.Connection,
    run_id: str,
    *,
    status: str,
    read: int = 0,
    loaded: int = 0,
    rejected: int = 0,
    error: str | None = None,
) -> None:
    # A failed publish leaves the connection aborted. Roll back before the audit write.
    conn.rollback()
    with conn.transaction():
        conn.execute(
            """
            UPDATE ops.ingest_runs
            SET status = %s,
                finished_at = %s,
                rows_read = %s,
                rows_loaded = %s,
                rows_rejected = %s,
                error_message = %s
            WHERE run_id = %s
            """,
            (status, utcnow(), read, loaded, rejected, error, run_id),
        )


def quarantine(
    conn: psycopg.Connection,
    *,
    run_id: str,
    source_id: str,
    record_key: str | None,
    reason_code: str,
    detail: str,
    raw: dict[str, Any],
) -> None:
    existing = conn.execute(
        """
        SELECT rejected_id FROM ops.rejected_records
        WHERE source_id = %s AND record_key IS NOT DISTINCT FROM %s AND reason_code = %s
        LIMIT 1
        """,
        (source_id, record_key, reason_code),
    ).fetchone()
    if existing:
        return
    conn.execute(
        """
        INSERT INTO ops.rejected_records
          (rejected_id, run_id, source_id, record_key, reason_code, detail, raw_json, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (new_id(), run_id, source_id, record_key, reason_code, detail, Jsonb(raw), utcnow()),
    )


def set_coverage(
    conn: psycopg.Connection,
    property_id: str,
    source_id: str,
    status: str,
    detail: str,
) -> None:
    conn.execute(
        """
        INSERT INTO ops.source_coverage (property_id, source_id, status, detail, checked_at)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (property_id, source_id) DO UPDATE SET
          status = EXCLUDED.status,
          detail = EXCLUDED.detail,
          checked_at = EXCLUDED.checked_at
        """,
        (property_id, source_id, status, detail, utcnow()),
    )
