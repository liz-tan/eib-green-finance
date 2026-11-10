# Green public finance, crowding in, and local growth — EIB data pipeline

Research data pipeline for the LSE project on whether EIB green lending crowds in
private investment and generates local economic outcomes (PI: Neil Lee).

This repository builds a **project-level dataset of EIB financed operations** from the
public projects portal, classifies them (green / sector / direct vs intermediated),
and attaches sub-national geography — the "treatment" side of the study.

> **Status:** pilot. The goal of the pilot is to prove the end-to-end pipeline on one
> small, hand-verifiable slice (one country × a few years), not to build the full panel.

---

## Data model

Three layers, built in order:

| Layer | Source | Grain | Key fields |
|---|---|---|---|
| **Spine** | Portal bulk export (`data/raw/loanExport.xlsx`) | signature × country | name, country, sector, signature date, signed amount (EUR), description |
| **Enrichment** | Project pages + PDFs (scraped) | project | project number/URL, promoter, environmental category, status, document (ESDS/NTS) text, place names |
| **Derived** | Our own classifiers | project | green share, sector/technology tags, direct-vs-intermediated flag, geocode (NUTS/coords) |

The **spine is already in hand** (the portal export). The scraper's job is to attach
project IDs and the enrichment layer, then our classifiers add the derived layer.

The annual **Climate Action & Sustainability "detailed list"** files (2016–2025) are kept
as a *benchmark / validation set* for the green classifier — not as the treatment, because
they start in 2016, change definition in 2021, cover ~95% of the portfolio, and carry only
country-level geography. See `docs/` for the full rationale.

## Pipeline

```
[0] Spine            portal "financed" export  ──►  data/raw/loanExport.xlsx   (done)
[1] Harvest IDs      listing (JS/API) ──► project number + URL per operation
[2] Join             attach IDs to spine on name + date + country + amount
[3] Enrich pages     project page ──► promoter, env category, status, PDF links
[4] Enrich PDFs      ESDS/NTS ──► location text, EIA category, capacity
[5] Classify         LLM ──► green share, sector/tech tags, intermediated flag   (next)
[6] Geocode          place-name extraction ──► NUTS / coords + manual check      (next)
[7] Output           tidy project-level panel  ──►  data/processed/
```

**The pilot runs stages 1–4** on the configured slice, plus a first pass at 5–6.

## Quick start

```bash
# 1. environment
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium          # for the listing harvester

# 2. put the portal export in place
#    (download from the portal with the "financed" filter, save as:)
#    data/raw/loanExport.xlsx

# 3. set the pilot slice
$EDITOR config/pilot.yaml             # country / years / sectors

# 4. run the pilot end to end
python scripts/run_pilot.py
```

Outputs land in `data/processed/` (the tidy table) and `data/interim/` (raw HTML/PDF cache,
harvested IDs). Raw caches are git-ignored.

## Harvesting IDs — two routes

The financed-projects list is rendered client-side, so the project rows (and the
`/en/projects/all/<id>` links we need) are **not** in the page HTML. Two ways to get them,
in `src/eibscraper/harvest_ids.py`:

1. **Headless browser (default).** Playwright renders the filtered list and reads the
   project links. Robust, but slower, and the CSS selectors may need a one-time tune against
   the live DOM (flagged in the code).
2. **Backend JSON endpoint (preferred once found).** Open the list in your browser, open
   DevTools → Network, apply a filter, and copy the XHR request the page makes. Drop that URL
   template into `harvest_ids.py` (`API_URL_TEMPLATE`) and the harvester hits it directly —
   faster and more stable than scraping the DOM.

## Repository layout

```
config/pilot.yaml          pilot scope (country, years, sectors)
data/raw/                   portal export + caches (git-ignored)
data/interim/              harvested IDs, parsed pages
data/processed/            final tidy tables
src/eibscraper/            the pipeline modules
scripts/run_pilot.py       orchestrates stages 1–4 on the slice
docs/                      project notes + GitHub Pages
tests/                     parser tests
```

## Data sources & caveats

- **Portal** (`eib.org/en/projects/all/<id>`): all signed contracts 1959–2026; structured
  geography is country-level only; sub-national location lives in free text + the ESDS/NTS PDFs.
- **Intermediated loans** ("Credit lines", ~28% of rows) have no public final beneficiary or
  site — flagged, not geocodable without EIB internal data.
- Be a polite client: the scraper rate-limits, caches, and retries (`utils.py`). Don't hammer
  the site; the cache means you only fetch each page once.

## Licence

MIT — see `LICENSE`. Research code; no data is committed to the repo.
