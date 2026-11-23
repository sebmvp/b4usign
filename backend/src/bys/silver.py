from __future__ import annotations

from pathlib import Path

import duckdb


def split_permits(jsonl_path: Path, valid_path: Path, rejected_path: Path) -> dict[str, int]:
    """DuckDB is the silver boundary: type checks and the publish/reject split."""
    valid_path.parent.mkdir(parents=True, exist_ok=True)
    if not jsonl_path.exists() or jsonl_path.stat().st_size == 0:
        return {"read": 0, "valid": 0, "rejected": 0}
    con = duckdb.connect()
    con.execute(
        "CREATE TABLE raw AS SELECT * FROM read_json_auto(?)",
        [str(jsonl_path)],
    )
    counts = con.execute(
        """
        SELECT
          count(*) AS read,
          count(*) FILTER (
            WHERE permit_number IS NOT NULL
              AND length(trim(permit_number)) > 0
              AND folio ~ '^[0-9]{13}$'
          ) AS valid,
          count(*) FILTER (
            WHERE permit_number IS NULL OR length(trim(permit_number)) = 0
          ) AS missing_number,
          count(*) FILTER (
            WHERE folio IS NULL OR folio !~ '^[0-9]{13}$'
          ) AS bad_folio
        FROM raw
        """
    ).fetchone()
    if counts[1]:
        con.execute(
            """
            COPY (
              SELECT * FROM raw
              WHERE permit_number IS NOT NULL
                AND length(trim(permit_number)) > 0
                AND folio ~ '^[0-9]{13}$'
            ) TO ? (FORMAT PARQUET)
            """,
            [str(valid_path)],
        )
    if counts[0] - counts[1]:
        con.execute(
            """
            COPY (
              SELECT *,
                CASE
                  WHEN permit_number IS NULL OR length(trim(permit_number)) = 0
                    THEN 'missing_permit_number'
                  WHEN folio IS NULL OR folio !~ '^[0-9]{13}$'
                    THEN 'invalid_folio'
                  ELSE 'rejected'
                END AS reason_code
              FROM raw
              WHERE NOT (
                permit_number IS NOT NULL
                AND length(trim(permit_number)) > 0
                AND folio ~ '^[0-9]{13}$'
              )
            ) TO ? (FORMAT PARQUET)
            """,
            [str(rejected_path)],
        )
    con.close()
    return {
        "read": int(counts[0]),
        "valid": int(counts[1]),
        "rejected": int(counts[0] - counts[1]),
        "missing_number": int(counts[2]),
        "bad_folio": int(counts[3]),
    }


def read_parquet(path: Path) -> list[dict]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    con = duckdb.connect()
    cursor = con.execute("SELECT * FROM read_parquet(?)", [str(path)])
    columns = [item[0] for item in cursor.description]
    rows = [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
    con.close()
    return rows
