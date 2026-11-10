# EIB green finance — project notes

Companion notes for the data pipeline in this repository. (To publish these as a
GitHub Pages site: repo **Settings → Pages → Source: `main` / `docs`**.)

## Why scrape when EIB publishes climate figures?

EIB's own Climate Action & Sustainability data is a good *benchmark* but cannot be the
treatment variable:

- starts 2016 (no pre-2015 baseline);
- the definition broke in 2021 (climate-only → climate + environmental sustainability);
- ~95% of the portfolio is now tagged green (little contrast);
- country-level geography only.

Our own classifier, run on portal descriptions (back to 1959), gives a definition-stable
green measure that spans the shock and can be geocoded below country level. The CAS annual
"detailed lists" (2016–2025) are kept as a labelled validation set.

## Identification options (summary)

1. **Firm-level** — EIBIS × Orbis; firm financing response + real outcomes. Best for the
   direct-recipient and propagation mechanisms.
2. **Just transition** — 112 designated NUTS3 territories, EIB Public Sector Loan Facility.
   Clean boundary discontinuity; **held in reserve** (post-2022, bundled funding) — a strong
   candidate for a follow-on with further funding.
3. **Urban** — city climate projects; staggered city DiD + within-city distance design.
   Best setting for the local-spillover mechanism.

## Pipeline status

- [x] Spine (portal export)
- [ ] Stage 1–4 pilot (this repo) — harvest IDs, enrich pages + PDFs, join
- [ ] Stage 5 classification (LLM green/sector/intermediated)
- [ ] Stage 6 geography (place-name extraction → NUTS, with manual validation)
- [ ] Scale from pilot slice to full EU panel
