# Decisions

## PostGIS on port 5433

Another Postgres already listens on 5432 on this Mac. The compose file publishes PostGIS on 127.0.0.1:5433 only.

## Property-scoped fetch, not a county load

The point layer has about 944,000 rows and this machine had about 13 GB free when the project started. Loading the county would fight the rule that a fetch must not assume the dataset fits in memory. The adapter pages. The product fetches the folio that was opened, plus its parent.

## County flood layer, not the national NFHL host

`hazards.fema.gov` reset the connection on 23 November 2026. The county FeatureServer layer 8 returned a zone for the checked points. The finding says it is a county copy and that the layer has no effective date.

## No model on the answer path by default

A small local model is installed on this machine (`qwen3.5:2b`). A rewrite can add a claim that the citation check would miss if the claim has no citation. The default answer is a template over retrieved findings. The model stays behind `BYS_USE_OLLAMA=1` and is discarded when the check fails.

## Docling is not in this version

There is no verified property PDF corpus in the repo, and private upload is not enabled. Document extraction is not implemented. The ask panel says so when the question needs a reserve study or an inspection report.
