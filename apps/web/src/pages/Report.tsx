import { FormEvent, useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { getJson, type Finding, type Report } from "../api";
import { MapPane } from "../components/MapPane";

const SUGGESTED = [
  "What does the permit history suggest I should ask about?",
  "What does the flood designation mean?",
  "Which public records are available for this property?",
  "Does this condo have enough money in reserves?",
];

export function ReportPage() {
  const { propertyId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const intent = params.get("intent") === "rent" ? "rent" : "buy";
  const use = params.get("use") === "house" ? "house" : "condo";
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState("");
  const [open, setOpen] = useState<Finding | null>(null);
  const [checked, setChecked] = useState<Record<string, boolean>>({});
  const [question, setQuestion] = useState(SUGGESTED[0]);
  const [answer, setAnswer] = useState<{ answer: string; citations: { citation_id: string; finding_id: string; label: string; url: string | null }[]; abstained: boolean; limitations: string[] } | null>(null);
  const [asking, setAsking] = useState(false);

  useEffect(() => {
    let cancel = false;
    setReport(null);
    setError("");
    setOpen(null);
    getJson<Report>(`/api/v1/properties/${propertyId}/report?intent=${intent}&use=${use}`)
      .then((body) => {
        if (!cancel) setReport(body);
      })
      .catch((exc: Error) => {
        if (!cancel) setError(exc.message);
      });
    return () => {
      cancel = true;
    };
  }, [propertyId, intent, use]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(null);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const groups = useMemo(() => {
    const order = ["Property identity", "Permit history", "Flood hazard designation"];
    const map = new Map<string, Finding[]>();
    for (const finding of report?.findings ?? []) {
      const list = map.get(finding.theme) ?? [];
      list.push(finding);
      map.set(finding.theme, list);
    }
    return [...map.entries()].sort((a, b) => order.indexOf(a[0]) - order.indexOf(b[0]));
  }, [report]);

  async function onAsk(event: FormEvent) {
    event.preventDefault();
    setAsking(true);
    try {
      const body = await fetch(`/api/v1/properties/${propertyId}/ask?intent=${intent}&use=${use}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      });
      const payload = await body.json();
      if (!body.ok) throw new Error(payload.detail || "Ask failed.");
      setAnswer(payload);
    } catch (exc) {
      setAnswer({
        answer: exc instanceof Error ? exc.message : "Ask failed.",
        citations: [],
        abstained: true,
        limitations: [],
      });
    } finally {
      setAsking(false);
    }
  }

  function copyChecklist() {
    if (!report) return;
    const text = report.checklist
      .map((item) => `${item.kind === "general" ? "General" : "From a record"}: ${item.text}`)
      .join("\n");
    void navigator.clipboard.writeText(text);
  }

  if (error) {
    return (
      <main className="page">
        <p className="error">{error}</p>
        <Link to="/">Back to search</Link>
      </main>
    );
  }
  if (!report) {
    return (
      <main className="page loading">
        <p className="kicker">Checking official records</p>
        <h1>Pulling the folio, the map, and the permit file.</h1>
        <p className="lede">This reads the county and city services. It can take a few seconds. Nothing on this page is a score.</p>
      </main>
    );
  }

  const property = report.property;
  return (
    <main className="page">
      <div className="report-head">
        <div>
          <Link to="/" className="muted no-print">Search another address</Link>
          <h1>{property.address}</h1>
          <div className="meta">
            <span>Folio {property.folio}</span>
            {property.parent_folio ? <span>Parent {property.parent_folio}</span> : null}
            <span>{property.municipality || "Municipality unresolved"}</span>
            <span>{property.official_use === "condo" ? "Condominium unit" : "House record"}</span>
            <span>Matched by official folio</span>
          </div>
        </div>
        <div className="toggles no-print">
          <div className="toggle" role="group" aria-label="Buy or rent">
            <button type="button" aria-pressed={intent === "buy"} onClick={() => setParams({ intent: "buy", use })}>Buy</button>
            <button type="button" aria-pressed={intent === "rent"} onClick={() => setParams({ intent: "rent", use })}>Rent</button>
          </div>
        </div>
      </div>
      {property.limitations ? <p className="limit">{property.limitations}</p> : null}
      {report.refresh_error ? <p className="error">Live refresh failed. Showing the last stored report. {report.refresh_error}</p> : null}

      <div className="layout">
        <div>
          {groups.map(([theme, findings]) => {
            const parentPermits = findings.filter((finding) => finding.attribution === "parent_folio");
            const primary = findings.filter((finding) => finding.attribution !== "parent_folio");
            return (
            <section className="group" key={theme}>
              <h2>{theme}</h2>
              <div className="stack">
                {primary.map((finding) => (
                  <button key={finding.id} className="finding" type="button" onClick={() => setOpen(finding)}>
                    <div className="theme">{finding.status.replaceAll("_", " ")}</div>
                    <h3>{finding.title}</h3>
                    <p>{finding.what}</p>
                    <p className="ask">{finding.ask}</p>
                  </button>
                ))}
                {parentPermits.length > 0 ? (
                  <details className="card">
                    <summary>{parentPermits.length} permits on the parent parcel, not this unit</summary>
                    <div className="stack" style={{ marginTop: 12 }}>
                      {parentPermits.map((finding) => (
                        <button key={finding.id} className="finding" type="button" onClick={() => setOpen(finding)}>
                          <h3>{finding.title}</h3>
                          <p>{finding.what}</p>
                        </button>
                      ))}
                    </div>
                  </details>
                ) : null}
              </div>
            </section>
            );
          })}
        </div>
        <aside className="stack">
          <section className="side-block">
            <h2>Map</h2>
            {property.lon != null && property.lat != null ? (
              <MapPane lon={property.lon} lat={property.lat} geometry={property.geometry} geometryKind={property.geometry_kind} />
            ) : (
              <p>No coordinates were published for this folio.</p>
            )}
            <p className="map-note">
              {property.geometry_kind === "parent_parcel"
                ? "Outline is the parent parcel, not the unit interior. The dot is the property-appraiser point."
                : property.geometry_kind === "parcel"
                  ? "Outline is the parcel polygon. The dot is the property-appraiser point."
                  : "Dot only. A point is not a surveyed building outline."}
              {" "}Basemap © OpenStreetMap contributors, via OpenFreeMap.
            </p>
          </section>
          <section className="side-block">
            <h2>What to ask</h2>
            {report.checklist.map((item) => (
              <label className="check" key={item.id}>
                <input
                  type="checkbox"
                  checked={Boolean(checked[item.id])}
                  onChange={() => setChecked((current) => ({ ...current, [item.id]: !current[item.id] }))}
                />
                <span>
                  <span className="kind">{item.kind === "general" ? "General guidance" : "From a record"}</span>
                  <br />
                  {item.text}
                </span>
              </label>
            ))}
            <div className="row-actions no-print">
              <button type="button" className="ghost" onClick={copyChecklist}>Copy</button>
              <button type="button" className="ghost" onClick={() => window.print()}>Print</button>
            </div>
          </section>
          <section className="side-block">
            <h2>Sources checked</h2>
            {report.coverage.map((row) => (
              <p key={row.source_id}>
                <strong>{row.label}.</strong> {row.detail}
              </p>
            ))}
            <p className="muted">Retrieved {report.retrieved_at || "unknown"}.</p>
          </section>
        </aside>
      </div>

      <section className="card ask-box no-print" style={{ marginTop: 28 }}>
        <p className="kicker">Ask this property</p>
        <h2>Questions stay on this folio.</h2>
        <div className="suggestions">
          {SUGGESTED.map((item) => (
            <button key={item} type="button" onClick={() => setQuestion(item)}>{item}</button>
          ))}
        </div>
        <form onSubmit={onAsk}>
          <textarea aria-label="Question" value={question} onChange={(event) => setQuestion(event.target.value)} />
          <div className="row-actions">
            <button className="solid" type="submit" disabled={asking}>{asking ? "Checking records" : "Ask"}</button>
          </div>
        </form>
        {answer ? (
          <div>
            <p>{answer.answer}</p>
            {answer.citations.map((citation) => (
              <button
                key={citation.citation_id}
                className="ghost"
                type="button"
                onClick={() => setOpen(report.findings.find((finding) => finding.id === citation.finding_id) || null)}
              >
                {citation.citation_id} · {citation.label}
              </button>
            ))}
            {answer.limitations.map((item) => (
              <p className="muted" key={item}>{item}</p>
            ))}
          </div>
        ) : null}
      </section>

      {open ? (
        <div className="drawer-back no-print" onClick={() => setOpen(null)}>
          <aside className="drawer" role="dialog" aria-label="Evidence" onClick={(event) => event.stopPropagation()}>
            <button type="button" className="ghost" onClick={() => setOpen(null)}>Close</button>
            <p className="theme">{open.source_name}</p>
            <h2>{open.title}</h2>
            <p>{open.what}</p>
            <p>{open.why}</p>
            <dl>
              <dt>Record</dt>
              <dd>{open.source_record_id || "Not published"}</dd>
              <dt>Event date</dt>
              <dd>{open.event_date || "Unknown"}</dd>
              <dt>Retrieved</dt>
              <dd>{open.retrieved_at || report.retrieved_at || "Unknown"}</dd>
              <dt>Attribution</dt>
              <dd>{open.attribution}</dd>
              {Object.entries(open.fields).map(([key, value]) => (
                <span key={key} style={{ display: "contents" }}>
                  <dt>{key}</dt>
                  <dd>{value == null ? "—" : String(value)}</dd>
                </span>
              ))}
            </dl>
            {open.caveat ? <p className="limit">{open.caveat}</p> : null}
            {open.source_url ? (
              <p><a href={open.source_url} target="_blank" rel="noreferrer">Open the source record</a></p>
            ) : null}
          </aside>
        </div>
      ) : null}
    </main>
  );
}
