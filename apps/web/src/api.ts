export type SearchHit = {
  property_id: string;
  folio: string;
  address: string;
  condo_flag: string | null;
  parent_folio: string | null;
  lon: number | null;
  lat: number | null;
};

export type Finding = {
  id: string;
  theme: string;
  status: string;
  title: string;
  what: string;
  why: string;
  ask: string;
  source_name: string;
  source_record_id: string | null;
  source_url: string | null;
  event_date: string | null;
  retrieved_at: string | null;
  attribution: string;
  fields: Record<string, unknown>;
  caveat: string;
};

export type Report = {
  property: {
    property_id: string;
    address: string | null;
    folio: string;
    parent_folio: string | null;
    condo_flag: string | null;
    official_use: string;
    municipality: string | null;
    match_status: string;
    match_method: string;
    lon: number | null;
    lat: number | null;
    geometry?: { type: string; coordinates: unknown } | null;
    geometry_kind: string;
    limitations: string;
    source_url: string;
  };
  intent: string;
  official_use: string;
  findings: Finding[];
  coverage: { source_id: string; status: string; label: string; detail: string; checked_at: string | null }[];
  checklist: { id: string; kind: "evidence" | "general"; text: string }[];
  buildings: {
    ubid: string;
    folio: string;
    address: string | null;
    year_built: number | null;
    units: number | null;
    floors: number | null;
    bldg_type: string | null;
  }[];
  retrieved_at: string | null;
  refresh_error?: string;
};

export async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof body.detail === "string" ? body.detail : "Request failed.";
    throw new Error(detail);
  }
  return body as T;
}
