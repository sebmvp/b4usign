Local data. Not committed.

- `bronze/` — original service responses for a fetch. Not edited after write.
- `silver/` — DuckDB Parquet. Valid permits and rejected permits are separate files.
- `gold/` — reserved. The serving copy is PostgreSQL, not a file in this folder.
- `documents/` — not used. Private uploads are not enabled.
