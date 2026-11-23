from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import DATA_ROOT
from .hashing import content_hash


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def write_bronze(
    source_id: str,
    run_id: str,
    pages: list[dict[str, Any]],
    query_text: str,
) -> tuple[Path, str]:
    dest = DATA_ROOT / "bronze" / source_id / run_id
    dest.mkdir(parents=True, exist_ok=True)
    hasher_parts: list[str] = []
    for index, page in enumerate(pages):
        raw = json.dumps(page, sort_keys=True, separators=(",", ":"), default=str)
        path = dest / f"page_{index:04d}.json"
        path.write_text(raw)
        hasher_parts.append(content_hash(raw))
    manifest = {
        "source_id": source_id,
        "run_id": run_id,
        "query": query_text,
        "pages": len(pages),
        "retrieved_at": utcnow().isoformat(),
    }
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return dest, content_hash(hasher_parts)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as handle:
        for row in rows:
            handle.write(json.dumps(row, default=str) + "\n")
