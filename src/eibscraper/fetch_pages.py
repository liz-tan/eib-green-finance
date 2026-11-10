"""Stage 3 — fetch each project page and parse structured fields + document links.

Project pages (eib.org/en/projects/all/<id>) are server-rendered, so plain
requests + BeautifulSoup works. The selectors below are reasonable defaults based
on the page layout; verify them against one real page and adjust the labels if the
markup differs (flagged with TODO(tune)).

Output: data/interim/pages_<slice>.csv  (+ per-project JSON cache)
"""
from __future__ import annotations
import json
import re
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

PDF_RE = re.compile(r"\.pdf($|\?)", re.I)


def _field_by_label(soup: BeautifulSoup, label: str) -> str | None:
    """Project pages render facts as label/value pairs. Find a value by its label."""
    node = soup.find(string=re.compile(rf"^\s*{re.escape(label)}\s*$", re.I))
    if not node:
        return None
    # value is usually the next sibling block / dd
    parent = node.find_parent()
    sib = parent.find_next_sibling() if parent else None
    return sib.get_text(" ", strip=True) if sib else None


def parse_project(html: str, project_id: str, url: str) -> dict:
    soup = BeautifulSoup(html, "lxml")

    title = soup.find("h1")
    rec = {
        "project_id": project_id,
        "url": url,
        "title": title.get_text(strip=True) if title else None,
        # TODO(tune): confirm these labels match the live page
        "status": _field_by_label(soup, "Status"),
        "sector": _field_by_label(soup, "Sector"),
        "promoter": _field_by_label(soup, "Promoter"),
        "env_category": _field_by_label(soup, "Environmental and Social"),
        "proposed_amount": _field_by_label(soup, "Proposed EIB finance"),
        "signed_amount": _field_by_label(soup, "Total cost"),
        "signature_date": _field_by_label(soup, "Signature date"),
    }

    # full description text (where sub-national place names often sit)
    main = soup.find("main") or soup
    rec["description"] = main.get_text(" ", strip=True)[:4000]

    # document links (ESDS / NTS / press release …) — the enrichment PDFs
    docs = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if PDF_RE.search(href):
            docs.append({"label": a.get_text(" ", strip=True)[:120],
                         "href": href if href.startswith("http") else f"https://www.eib.org{href}"})
    rec["documents"] = docs
    rec["n_pdfs"] = len(docs)
    return rec


def run(cfg, fetcher, ids_csv: Path) -> Path:
    ids = pd.read_csv(ids_csv, dtype={"project_id": str})
    cache = Path("data/interim/pages_json")
    cache.mkdir(parents=True, exist_ok=True)

    records = []
    for _, row in ids.iterrows():
        pid, url = str(row["project_id"]), row["url"]
        html = fetcher.get_text(url)
        rec = parse_project(html, pid, url)
        (cache / f"{pid}.json").write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
        records.append(rec)

    df = pd.DataFrame(records)
    out = ids_csv.parent / ids_csv.name.replace("ids_", "pages_")
    df.drop(columns=["documents"]).to_csv(out, index=False)
    print(f"[fetch_pages] parsed {len(df)} pages ({df['n_pdfs'].sum()} PDFs found) -> {out}")
    return out
