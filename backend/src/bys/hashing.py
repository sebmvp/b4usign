from __future__ import annotations

import hashlib
import json
from typing import Any


def content_hash(payload: Any) -> str:
    """Hash the full canonical payload, not the identifier alone."""
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode()).hexdigest()
