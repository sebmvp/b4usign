# Before You Sign

This file is for later work in this repository. The product spec the owner wrote is not copied here. Code and the docs in `docs/` win when they disagree.

## Product

A person is about to rent or buy in Miami-Dade. Show the official folio, the records that actually attach to it, and what was not searched. Do not invent a finding, a citation, or a clean result from a missing source.

## Do not

- Load the whole county into memory. Page, and fetch the folio that was opened.
- Cast a folio to a number. It is a 13-digit string.
- Link two folios because the street address matches. The parent folio is the only related folio. Sibling units of that parent are not collisions. A different folio on the same street is refused.
- Search City of Miami permits unless the municipal code is `01`.
- Treat permit status as proof the work is finished.
- Treat flood zone as a prediction. The county flood layer has no map effective date. `ELEV` of `-9999` is unpublished, not an elevation.
- Put a language model on the path that decides a match or adds a fact. Template answers cite findings already on the report. If `BYS_USE_OLLAMA=1`, discard model text that adds a banned claim or an unknown citation.
- Enable public document upload. It is not built.
- Use port 5432. Another Postgres already listens there. This app uses 5433.

## Layout

`backend/src/bys/` is the API, fetch, and report. `apps/web/` is the React app. `migrations/` is the only schema authority. `data/` is local and gitignored except this note.
