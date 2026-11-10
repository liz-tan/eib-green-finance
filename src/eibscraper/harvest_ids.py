"""Stage 1 — harvest project numbers + URLs for the configured slice.

The financed-projects list is rendered client-side, so the project links are not
in the static HTML. Two routes:

  (A) Playwright (default): render the filtered list, read the /projects/all/<id>
      links. Robust; selectors may need a one-time tune against the live DOM.
  (B) API (preferred once found): if you paste the backend XHR URL template into
      config -> harvest.api_url_template, we hit it directly (fast, stable).

Output: data/interim/ids_<slice>.csv  with columns
        [project_id, url, name, country, sector, signature_date, amount_text]
"""
from __future__ import annotations
import re
import urllib.parse as up
from pathlib import Path

import pandas as pd

LIST_URL = "https://www.eib.org/en/projects/loans/index.htm"
PROJECT_RE = re.compile(r"/en/projects/all/(\d+)")


# ---------------------------------------------------------------------------
# Route A — Playwright
# ---------------------------------------------------------------------------
def harvest_with_browser(country: str, years: list[int], sectors: list[str],
                         headless: bool = True) -> pd.DataFrame:
    from playwright.sync_api import sync_playwright

    params = {"from": min(years), "to": max(years)}
    # NOTE: the portal uses short codes for country/sector in the query string
    # (e.g. ?sectors=EN). The simplest robust approach is to apply the filters in
    # the UI after load; here we pass year range via URL and filter client-side.
    url = LIST_URL + "?" + up.urlencode(params)

    rows: list[dict] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        page = browser.new_page()
        page.goto(url, wait_until="networkidle", timeout=60_000)

        # TODO(tune): set the country/sector filters via the on-page controls here
        # if URL params don't take. Inspect the live DOM once and adjust selectors.
        # e.g. page.select_option("#country-select", label=country)

        # Paginate: click "next" until it disappears. Selector likely needs tuning.
        while True:
            page.wait_for_timeout(1500)
            html = page.content()
            for m in PROJECT_RE.finditer(html):
                pid = m.group(1)
                rows.append({"project_id": pid,
                             "url": f"https://www.eib.org/en/projects/all/{pid}"})
            nxt = page.query_selector("a[rel=next], .pagination-next, button[aria-label*=Next]")
            if not nxt or not nxt.is_enabled():
                break
            nxt.click()
        browser.close()

    df = pd.DataFrame(rows).drop_duplicates("project_id").reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# Route B — backend JSON endpoint (fill api_url_template once you find it)
# ---------------------------------------------------------------------------
def harvest_with_api(fetcher, api_url_template: str, country: str,
                     years: list[int], sectors: list[str]) -> pd.DataFrame:
    """api_url_template may contain {page},{from},{to},{country},{sector}.

    Inspect the real response shape in DevTools and adjust the field names below.
    """
    rows, page = [], 1
    while True:
        url = api_url_template.format(page=page, **{"from": min(years), "to": max(years),
                                                    "country": country,
                                                    "sector": ",".join(sectors)})
        data = fetcher.get_json(url)
        items = data.get("results") or data.get("items") or data.get("data") or []
        if not items:
            break
        for it in items:
            pid = str(it.get("id") or it.get("projectNumber") or "")
            rows.append({
                "project_id": pid,
                "url": f"https://www.eib.org/en/projects/all/{pid}",
                "name": it.get("name") or it.get("title"),
                "country": it.get("country"),
                "sector": it.get("sector"),
                "signature_date": it.get("signatureDate") or it.get("date"),
                "amount_text": it.get("signedAmount") or it.get("amount"),
            })
        page += 1
    return pd.DataFrame(rows).drop_duplicates("project_id").reset_index(drop=True)


def run(cfg, fetcher) -> Path:
    s = cfg["slice"]
    tmpl = cfg["harvest"].get("api_url_template", "").strip()
    if tmpl:
        df = harvest_with_api(fetcher, tmpl, s["country"], s["years"], s["sectors"])
    else:
        df = harvest_with_browser(s["country"], s["years"], s["sectors"])

    out = Path("data/interim") / f"ids_{s['country'].lower()}_{min(s['years'])}-{max(s['years'])}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    print(f"[harvest_ids] {len(df)} project IDs -> {out}")
    return out
