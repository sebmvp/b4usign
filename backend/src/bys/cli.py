from __future__ import annotations

import sys

from .pipeline import resolve_property
from .sources import GOLD_SET


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else "help"
    if command == "seed":
        failed = 0
        for item in GOLD_SET:
            print(f"resolving {item['folio']}  {item['label']}", flush=True)
            try:
                property_id = resolve_property(item["folio"])
            except Exception as exc:
                failed += 1
                print(f"failed {item['folio']}: {exc}", flush=True)
                continue
            print(f"loaded {property_id}", flush=True)
        raise SystemExit(failed)
    if command == "resolve" and len(sys.argv) > 2:
        print(resolve_property(sys.argv[2]))
        return
    print("usage: python -m bys.cli seed | python -m bys.cli resolve FOLIO")
    raise SystemExit(2)


if __name__ == "__main__":
    main()
