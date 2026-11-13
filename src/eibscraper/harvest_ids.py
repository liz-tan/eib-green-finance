"""Stage 1 — harvest project IDs (+ core fields) from the EIB backend list API.

The portal grid is served by a JSON endpoint:
    https://www.eib.org/provider-eib-plr/app/loans/list?...&pageNumber=N&itemPerPage=K

Each record carries exactly what we need — `id` (project number), `url`, `title`,
`description`, `startDate` (signature date, epoch ms), an amount string, and structured
country / region / sector tags. So this replaces the old Playwright approach entirely,
and also supplies most of the spine fields next to the ID.

We page through the whole signed list once (cached), then filter to the configured
slice (country + years) client-side — robust without guessing the site's filter params.

Output: data/interim/ids_<slice>.csv
"""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

LIST_URL = "https://www.eib.org/provider-eib-plr/app/loans/list"
PROJECT_URL = "https://www.eib.org/en/projects/all/{}"

# fixed query params (mirror the portal's own request; no status/country filter here —
# we filter client-side below)
BASE_PARAMS = (
    "sortColumn=loanParts.loanPartStatus.statusDate&sortDir=desc"
    "&pageable=true&language=EN&defaultLanguage=EN"
    "&orLoanPartYearFrom=true&orLoanPartYearTo=true"
    "&orCountries.region=true&orCountries=true&orSectors=true"
)


def _tag(rec: dict, sub: str):
    for t in (rec.get("primaryTags") or []):
        if t.get("subType") == sub:
            return t.get("label"), t.get("value")
    return None, None


def _epoch_to_date(ms):
    if not ms:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date().isoformat()


def _amount(rec: dict):
    for x in (rec.get("additionalInformation") or []):
        if isinstance(x, str) and x.strip().startswith(("€", "$", "£")):
            return x.strip()
    return None


def fetch_all(fetcher, item_per_page: int = 200) -> pd.DataFrame:
    """Page through the full signed list, cached. Stops on the last (short) page."""
    rows, page = [], 0
    while True:
        url = f"{LIST_URL}?{BASE_PARAMS}&pageNumber={page}&itemPerPage={item_per_page}"
        payload = fetcher.get_json(url)
        data = payload.get("data") or []
        if not data:
            break
        for rec in data:
            c_label, c_val = _tag(rec, "countries")
            r_label, _ = _tag(rec, "regions")
            s_label, s_val = _tag(rec, "sectors")
            rows.append({
                "project_id": rec.get("id"),
                "url": PROJECT_URL.format(rec.get("url") or rec.get("id")),
                "title": rec.get("title"),
                "country": c_label, "country_code": c_val,
                "region": r_label,
                "sector": s_label, "sector_code": s_val,
                "signature_date": _epoch_to_date(rec.get("startDate")),
                "amount_text": _amount(rec),
                "description": rec.get("description"),   # may be truncated; full text on the page
            })
        print(f"[harvest_ids] page {page}: {len(data)} records")
        if len(data) < item_per_page:
            break
        page += 1
    return pd.DataFrame(rows)


def run(cfg, fetcher) -> Path:
    s = cfg["slice"]
    ipp = cfg.get("harvest", {}).get("item_per_page", 200)
    df = fetch_all(fetcher, item_per_page=ipp)

    # filter to the slice: country (by label or ISO code) + signature year
    yrs = set(s["years"])
    df["sig_year"] = pd.to_datetime(df["signature_date"], errors="coerce").dt.year
    mask = (
        df["country"].str.contains(s["country"], case=False, na=False)
        | df["country_code"].fillna("").str.upper().eq(str(s["country"]).upper())
    ) & df["sig_year"].isin(yrs)
    if s.get("sectors"):
        mask &= df["sector"].isin(s["sectors"])
    out_df = df[mask].drop(columns=["sig_year"]).reset_index(drop=True)

    out = Path("data/interim") / f"ids_{s['country'].lower()}_{min(s['years'])}-{max(s['years'])}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(out, index=False)
    print(f"[harvest_ids] {len(out_df)} projects in slice (of {len(df)} total) -> {out}")
    return out
