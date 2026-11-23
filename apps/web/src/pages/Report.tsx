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

function displayAddress(value: string | null) {
  if (!value) return "Address not published";
  return value.toLowerCase().replace(/\b([a-z])/g, (letter) => letter.toUpperCase());
}

function statusWord(finding: Finding) {
  const raw = String(finding.fields.PermitStatus || finding.title.split("·")[0] || "").trim();
  if (!raw) return "Permit";
  return raw.charAt(0).toUpperCase() + raw.slice(1).toLowerCase();
}

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

  const rows = useMemo(() => {
    if (!report) return [];
    const unit = report.findings.filter((finding) => finding.attribution === "unit_folio");
    const parent = report.findings.filter((finding) => finding.attribution === "parent_folio");
    const flood = report.findings.find((finding) => finding.theme.startsWith("Flood"));
    const refused = report.findings.find((finding) => finding.attribution === "refused_address_match");
    const next: { key: string; word: string; text: string; hot?: boolean; finding: Finding | null }[] = unit.map((finding) => {
      const scope = String(finding.fields.ScopeOfWork || "").trim();
      const short = scope && scope.length < 72 ? scope : "On this unit.";
      return {
        key: finding.id,
        word: statusWord(finding),
        text: statusWord(finding).toLowerCase() === "final"
          ? `${short} Final is the city's word, not an inspection.`
          : `${short} Ask if the work is finished.`,
        hot: statusWord(finding).toLowerCase() === "active",
        finding,
      };
    });
    if (parent.length) {
      next.push({
        key: "parent",
        word: String(parent.length),
        text: "Permits on the parent parcel. Not this unit.",
        finding: null,
      });
    }
    if (flood) {
      const zone = flood.fields.FZONE ? String(flood.fields.FZONE) : flood.title;
      next.push({
        key: flood.id,
        word: zone,
        text: flood.status === "checked_none" ? flood.what : "Flood zone at this point. Not a forecast.",
        finding: flood,
      });
    }
    if (refused) {
      next.push({
        key: refused.id,
        word: "No",
        text: "Same-street folio was not linked.",
        finding: refused,
      });
    }
    return next;
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
  const parentPermits = report.findings.filter((finding) => finding.attribution === "parent_folio");
  const where = [
    property.municipality ? displayAddress(property.municipality) : "Municipality unresolved",
    property.official_use === "condo" ? "condominium unit" : "house record",
  ].join(" ");

  return (
    <main className="sheet-page">
      <div className="sheet-stage">
        {property.lon != null && property.lat != null ? (
          <MapPane
            lon={property.lon}
            lat={property.lat}
            geometry={property.geometry}
            geometryKind={property.geometry_kind}
            sheet
          />
        ) : (
          <p className="map-missing">No coordinates were published for this folio.</p>
        )}
        <aside className="sheet">
          <div className="sheet-top">
            <Link to="/" className="mark">Before You Sign</Link>
            <div className="seg" role="group" aria-label="Buy or rent">
              <button type="button" aria-pressed={intent === "buy"} onClick={() => setParams({ intent: "buy", use })}>Buy</button>
              <button type="button" aria-pressed={intent === "rent"} onClick={() => setParams({ intent: "rent", use })}>Rent</button>
            </div>
          </div>
          <h1>{displayAddress(property.address)}</h1>
          <p className="where">{where}</p>
          {rows.map((row) => (
            <button
              key={row.key}
              type="button"
              className="scan"
              onClick={() => {
                if (row.finding) setOpen(row.finding);
                else document.getElementById("parent-permits")?.scrollIntoView({ behavior: "smooth" });
              }}
            >
              <span className={row.hot ? "word hot" : "word"}>{row.word}</span>
              <span>{row.text}</span>
            </button>
          ))}
          <p className="note">
            {property.geometry_kind === "parent_parcel"
              ? "The gold line is the parent parcel, not the unit."
              : property.geometry_kind === "parcel"
                ? "The gold line is the parcel polygon."
                : "The dot is a point. It is not a surveyed outline."}
          </p>
          <p className="folio">Folio {property.folio}{property.parent_folio ? ` · Parent ${property.parent_folio}` : ""}</p>
        </aside>
      </div>

      {property.limitations ? <p className="limit page-pad">{property.limitations}</p> : null}
      {report.refresh_error ? <p className="error page-pad">Live refresh failed. Showing the last stored report. {report.refresh_error}</p> : null}

      <div className="page-pad below">
        {parentPermits.length > 0 ? (
          <details className="card" id="parent-permits">
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

        <div className="layout">
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
        </div>

        <section className="card ask-box no-print">
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

      </div>

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
