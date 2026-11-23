# Architecture

Official service → bronze JSON on disk → DuckDB Parquet for permits → PostgreSQL/PostGIS → FastAPI → React.

DuckDB is the analytical step for the permit split: a row is published only when it has a permit number and a 13-digit folio. PostgreSQL is the database the app reads. PostGIS holds parcel geometry and municipal polygons so a point can be checked locally. The flood zone is not stored as a polygon.

Iceberg, Spark, Trino, Airflow, and a separate vector database are not used. They are not needed for a property-scoped fetch.

Identity is the folio the person selected. A parent folio is stored beside it. Address similarity does not create a link. That decision is written to `ops.match_reviews`.

Ask This Property does not call a model by default. It classifies the question and answers from the findings already on the report, or it abstains. `BYS_USE_OLLAMA=1` may rewrite the answer. The rewrite is dropped if it cites an id that was not retrieved, or if it adds a claim the records do not support.
