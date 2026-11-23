import { useEffect, useState } from "react";
import { getJson } from "../api";

type Source = {
  source_id: string;
  publisher: string;
  title: string;
  layer_url: string;
  coverage_note: string;
  record_grain: string;
  status: string;
};

export function SourcesPage() {
  const [sources, setSources] = useState<Source[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    getJson<{ sources: Source[] }>("/api/v1/sources")
      .then((body) => setSources(body.sources))
      .catch((exc: Error) => setError(exc.message));
  }, []);

  return (
    <main className="page">
      <p className="kicker">Method</p>
      <h1>What this report can and cannot say.</h1>
      <p className="lede">
        Every finding names the record it came from. A source that was not searched is labeled.
        Missing records are not treated as a clean property.
      </p>
      {error ? <p className="error">{error}</p> : null}
      <div className="stack" style={{ marginTop: 28 }}>
        {sources.map((source) => (
          <article className="card" key={source.source_id}>
            <p className="theme">{source.status.replaceAll("_", " ")}</p>
            <h2>{source.title}</h2>
            <p>{source.publisher}. Grain: {source.record_grain}.</p>
            <p>{source.coverage_note}</p>
            {source.layer_url ? <p><a href={source.layer_url}>Source service</a></p> : null}
          </article>
        ))}
      </div>
    </main>
  );
}
