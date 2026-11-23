import { useEffect, useState } from "react";
import { getJson } from "../api";

type Run = {
  run_id: string;
  source_id: string;
  status: string;
  started_at: string;
  rows_read: number;
  rows_loaded: number;
  rows_rejected: number;
  query_text: string | null;
  error_message: string | null;
};

export function EngineeringPage() {
  const [body, setBody] = useState<{
    runs: Run[];
    rejected: { source_id: string; record_key: string; reason_code: string; detail: string }[];
    counts: { properties: number; permits: number; rejected: number; permit_versions: number };
  } | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getJson<NonNullable<typeof body>>("/api/v1/engineering")
      .then(setBody)
      .catch((exc: Error) => setError(exc.message));
  }, []);

  return (
    <main className="page">
      <p className="kicker">Records log</p>
      <h1>What was fetched, held back, and stored.</h1>
      <p className="lede">
        This page is for local development. It does not start an ingest, and it does not accept SQL.
      </p>
      {error ? <p className="error">{error}</p> : null}
      {body ? (
        <>
          <p>
            {body.counts.properties} properties · {body.counts.permits} published permits ·{" "}
            {body.counts.rejected} held back · {body.counts.permit_versions} permit versions
          </p>
          <table>
            <thead>
              <tr>
                <th>Status</th>
                <th>Source</th>
                <th>Query</th>
                <th>Read</th>
                <th>Loaded</th>
                <th>Held back</th>
              </tr>
            </thead>
            <tbody>
              {body.runs.map((run) => (
                <tr key={run.run_id}>
                  <td>{run.status}</td>
                  <td>{run.source_id}</td>
                  <td>{run.query_text}</td>
                  <td>{run.rows_read}</td>
                  <td>{run.rows_loaded}</td>
                  <td>{run.rows_rejected}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <h2>Held back</h2>
          {body.rejected.length === 0 ? <p>No rejected records yet.</p> : null}
          <ul>
            {body.rejected.map((row) => (
              <li key={`${row.record_key}-${row.reason_code}`}>
                {row.reason_code}: {row.record_key}. {row.detail}
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </main>
  );
}
