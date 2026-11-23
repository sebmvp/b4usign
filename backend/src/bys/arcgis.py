from __future__ import annotations

import time
from typing import Any

import httpx

from .config import USER_AGENT


class ArcGISError(RuntimeError):
    pass


class ArcGISClient:
    def __init__(self, client: httpx.Client | None = None, pause_s: float = 0.15) -> None:
        self.client = client or httpx.Client(
            timeout=httpx.Timeout(45.0),
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        )
        self.pause_s = pause_s
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def query(self, layer_url: str, params: dict[str, Any]) -> dict[str, Any]:
        query = {"f": "json", **params}
        last_error: Exception | None = None
        for attempt in range(4):
            try:
                response = self.client.get(f"{layer_url}/query", params=query)
                if response.status_code in {429, 500, 502, 503, 504}:
                    time.sleep(min(8, 2**attempt))
                    last_error = ArcGISError(f"{response.status_code} from {layer_url}")
                    continue
                response.raise_for_status()
                payload = response.json()
                if payload.get("error"):
                    raise ArcGISError(str(payload["error"]))
                time.sleep(self.pause_s)
                return payload
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                last_error = exc
                time.sleep(min(8, 2**attempt))
        raise ArcGISError(f"query failed for {layer_url}: {last_error}")

    def metadata(self, layer_url: str) -> dict[str, Any]:
        response = self.client.get(layer_url, params={"f": "json"})
        response.raise_for_status()
        return response.json()

    def pages(
        self,
        layer_url: str,
        where: str,
        out_fields: str,
        *,
        page_size: int = 1000,
        object_id_field: str = "OBJECTID",
        extra: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Page with a stable order. A repeated page does not loop forever."""
        features: list[dict[str, Any]] = []
        seen: set[Any] = set()
        offset = 0
        while offset < 20000:
            params: dict[str, Any] = {
                "where": where,
                "outFields": out_fields,
                "returnGeometry": "true",
                "outSR": "4326",
                "resultRecordCount": page_size,
                "resultOffset": offset,
                "orderByFields": object_id_field,
            }
            if extra:
                params.update(extra)
            page = self.query(layer_url, params)
            batch = page.get("features") or []
            if not batch:
                break
            added = 0
            for feature in batch:
                oid = (feature.get("attributes") or {}).get(object_id_field)
                key = oid if oid is not None else id(feature)
                if key in seen:
                    continue
                seen.add(key)
                features.append(feature)
                added += 1
            if added == 0 or len(batch) < page_size:
                break
            offset += len(batch)
        return features
