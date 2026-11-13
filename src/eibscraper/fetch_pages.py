"""Stage 3 — enrich each project from its page, MERGED onto the API row.

Keeps the reliable fields harvest_ids already got from the list API (country, sector,
signature date, amount) and adds page-only enrichment:
  - location_countries  (ALL countries — captures multi-country projects)
  - sector_detailed     (e.g. "Industry - Manufacturing")
  - status, signed_date_page  (from the "Signed | DD/MM/YYYY" line)
  - proposed_eib_finance, total_cost   (best-effort; see note)
  - promoter            (best-effort; see note)
  - objectives / environmental_aspects / procurement  (description, split)
  - description_full, documents (PDF links), n_pdfs

Extraction uses robust anchors (country/sector hrefs) and text patterns, not DOM
sibling position. Two fields are marked BEST-EFFORT — verify on a live page:
  * amount pairing (first EUR = proposed, second = total) assumes that order;
  * promoter (the value after the "Promoter - financial intermediary" label).
"""
from __future__ import annotations
import json
import re
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

PDF_RE = re.compile(r"\.pdf($|\?)", re.I)
STATUS_RE = re.compile(r"\b(Signed|Approved|Under appraisal|Dropped)\s*\|\s*(\d{2}/\d{2}/\d{4})")
EUR_RE = re.compile(r"EUR\s*[\d.,]+\s*(?:million|billion|m|bn)?", re.I)
SECTIONS = ["Objectives", "Environmental aspects", "Procurement", "Technical description"]


def _countries(soup):
    names, codes = [], []
    for a in soup.select('a[href*="countries="]'):
        code = re.search(r"countries=([A-Za-z]{2})", a["href"])
        nm = a.get_text(" ", strip=True)
        if nm:
            names.append(nm)
        if code:
            codes.append(code.group(1).upper())
    # dedupe preserving order
    names = list(dict.fromkeys(names))
    codes = list(dict.fromkeys(codes))
    return "; ".join(names), "; ".join(codes)


def _sector_detailed(soup):
    for a in soup.select('a[href*="sectors="]'):
        base = a.get_text(" ", strip=True)
        tail = (a.next_sibling or "")
        tail = tail if isinstance(tail, str) else ""
        full = (base + " " + tail).strip(" -–\t\n")
        if base:
            return re.sub(r"\s+", " ", full)
    return None


def _split_description(text):
    out = {"objectives": None, "environmental_aspects": None,
           "procurement": None, "technical_description": None}
    key = {"Objectives": "objectives", "Environmental aspects": "environmental_aspects",
           "Procurement": "procurement", "Technical description": "technical_description"}
    # build a regex that finds each heading and captures up to the next heading
    pat = re.compile(r"(" + "|".join(re.escape(h) for h in SECTIONS) + r")")
    parts = pat.split(text)
    # parts = [pre, heading, body, heading, body, ...]
    for i in range(1, len(parts) - 1, 2):
        h = parts[i].strip()
        body = parts[i + 1].strip()
        if h in key and body:
            out[key[h]] = body[:2000]
    return out


def _promoter(text: str, title: str | None) -> str | None:
    """Value after the 'Promoter - financial intermediary' label. The two-column layout
    puts the title line first, so skip it (we know the title from the API)."""
    idx = text.find("Promoter")
    if idx == -1:
        return None
    for ln in (l.strip() for l in text[idx:].split("\n")[1:]):
        if not ln or ln in ("Project name",):
            continue
        if title and ln.strip() == title.strip():
            continue
        return ln
    return None


def parse_project(html: str, title: str | None = None) -> dict:
    soup = BeautifulSoup(html, "lxml")
    main = soup.find("main") or soup
    text = main.get_text("\n", strip=True)

    rec = {}
    # status + signature date (as shown on the page)
    m = STATUS_RE.search(text)
    rec["status"] = m.group(1) if m else None
    rec["signed_date_page"] = m.group(2) if m else None

    # all countries (multi-country aware) + detailed sector
    rec["location_countries"], rec["location_country_codes"] = _countries(soup)
    rec["sector_detailed"] = _sector_detailed(soup)

    # amounts — BEST-EFFORT: first EUR figure = proposed, second = total cost.
    # Scope to the summary sheet (before the Description block) so description figures
    # don't leak in.
    flat = main.get_text(" ", strip=True)
    cut = min([p for p in (flat.find("Description"), flat.find("Objectives")) if p != -1]
              or [len(flat)])
    amts = [re.sub(r"\s+", " ", a.strip()) for a in EUR_RE.findall(flat[:cut])]
    rec["proposed_eib_finance"] = amts[0] if len(amts) >= 1 else None
    rec["total_cost"] = amts[1] if len(amts) >= 2 else None

    # promoter — value after the promoter label (title line skipped)
    rec["promoter"] = _promoter(text, title)

    # description sections
    rec.update(_split_description(text))
    rec["description_full"] = text[:6000]

    # document (PDF) links
    docs = []
    for a in soup.find_all("a", href=True):
        if PDF_RE.search(a["href"]):
            href = a["href"]
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
    for _, idrow in ids.iterrows():
        pid, url = str(idrow["project_id"]), idrow["url"]
        html = fetcher.get_text(url)
        enrich = parse_project(html, title=idrow.get("title"))
        merged = {**idrow.to_dict(), **enrich}   # API fields win on overlap; enrich adds the rest
        (cache / f"{pid}.json").write_text(json.dumps(merged, ensure_ascii=False, default=str),
                                           encoding="utf-8")
        records.append(merged)

    df = pd.DataFrame(records)
    out = ids_csv.parent / ids_csv.name.replace("ids_", "pages_")
    df.drop(columns=["documents"], errors="ignore").to_csv(out, index=False)
    print(f"[fetch_pages] enriched {len(df)} projects "
          f"({df['n_pdfs'].sum()} PDFs found) -> {out}")
    return out
