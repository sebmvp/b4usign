import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { getJson, type SearchHit } from "../api";

const EXAMPLES = [
  {
    id: "mdc-folio-0141381500010",
    address: "495 Brickell Ave 401",
    note: "Condominium unit · Miami",
    use: "condo",
  },
  {
    id: "mdc-folio-0141210131000",
    address: "3598 Avocado Ave",
    note: "House · Miami",
    use: "house",
  },
  {
    id: "mdc-folio-0341080770010",
    address: "1 Alhambra Cir 201",
    note: "Condominium unit · Coral Gables",
    use: "condo",
  },
];

export function LandingPage() {
  const navigate = useNavigate();
  const [intent, setIntent] = useState<"buy" | "rent">("buy");
  const [use, setUse] = useState<"house" | "condo">("condo");
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    if (query.trim().length < 3) {
      setHits([]);
      return;
    }
    const handle = window.setTimeout(() => {
      getJson<{ results: SearchHit[] }>(`/api/v1/properties/search?q=${encodeURIComponent(query)}`)
        .then((body) => {
          setHits(body.results);
          setError("");
        })
        .catch((exc: Error) => setError(exc.message));
    }, 280);
    return () => window.clearTimeout(handle);
  }, [query]);

  function open(hit: SearchHit) {
    const nextUse = hit.condo_flag === "Y" ? "condo" : use;
    navigate(`/property/${hit.property_id}?intent=${intent}&use=${nextUse}`);
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (hits[0]) open(hits[0]);
  }

  return (
    <main className="page">
      <p className="kicker">Miami-Dade public records</p>
      <h1>
        The listing looks great.
        <br />
        <em>What about the building?</em>
      </h1>
      <p className="lede">
        Explore public records, understand what matters, and know what to ask before you sign.
      </p>
      <form className="search-card" onSubmit={onSubmit}>
        <div className="toggles">
          <div className="toggle" role="group" aria-label="Buy or rent">
            <button type="button" aria-pressed={intent === "buy"} onClick={() => setIntent("buy")}>
              Buy
            </button>
            <button type="button" aria-pressed={intent === "rent"} onClick={() => setIntent("rent")}>
              Rent
            </button>
          </div>
          <div className="toggle" role="group" aria-label="House or condo">
            <button type="button" aria-pressed={use === "house"} onClick={() => setUse("house")}>
              House
            </button>
            <button type="button" aria-pressed={use === "condo"} onClick={() => setUse("condo")}>
              Condo
            </button>
          </div>
        </div>
        <div className="search-row">
          <input
            aria-label="Address"
            placeholder="Search a Miami-Dade address"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            autoComplete="off"
          />
          <button type="submit">Search</button>
        </div>
        {error ? <p className="error">{error}</p> : null}
        {hits.length > 0 ? (
          <ul className="hits">
            {hits.map((hit) => (
              <li key={hit.property_id}>
                <button type="button" className="text-link" onClick={() => open(hit)}>
                  <span>{hit.address}</span>
                  <small>
                    Folio {hit.folio}
                    {hit.condo_flag === "Y" ? " · condo unit" : ""}
                  </small>
                </button>
              </li>
            ))}
          </ul>
        ) : null}
      </form>
      <p className="coverage-note">
        County parcel records cover Miami-Dade. City of Miami permits are searched only when the
        property point falls inside the City of Miami. A missing record is not a clean building.
      </p>
      <h2>Verified examples</h2>
      <ul className="examples">
        {EXAMPLES.map((item) => (
          <li key={item.id}>
            <Link to={`/property/${item.id}?intent=${intent}&use=${item.use}`}>
              <span>{item.address}</span>
              <small>{item.note}</small>
            </Link>
          </li>
        ))}
      </ul>
    </main>
  );
}
