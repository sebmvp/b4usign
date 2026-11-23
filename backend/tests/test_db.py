import pytest

from bys.db import connect, finish_run, start_run


@pytest.mark.integration
def test_failed_statement_does_not_publish_and_audit_still_writes():
    conn = connect()
    run_id = start_run(conn, "test_rollback", "forced failure")
    object_id = "test-rollback-should-not-remain"
    try:
        with conn.transaction():
            conn.execute(
                """
                INSERT INTO evidence.permits (
                  source_object_id, permit_number, folio, content_hash, raw_json, retrieved_at
                ) VALUES (%s, 'TEST-ROLLBACK', '0141381500010', 'abc', '{}'::jsonb, now())
                """,
                (object_id,),
            )
            conn.execute("SELECT * FROM does_not_exist")
    except Exception as exc:
        finish_run(conn, run_id, status="failed", error=str(exc))
    left = conn.execute(
        "SELECT count(*) AS n FROM evidence.permits WHERE source_object_id = %s",
        (object_id,),
    ).fetchone()
    audit = conn.execute(
        "SELECT status, error_message FROM ops.ingest_runs WHERE run_id = %s",
        (run_id,),
    ).fetchone()
    conn.close()
    assert left["n"] == 0
    assert audit["status"] == "failed"
    assert "does_not_exist" in audit["error_message"]
