"""Stage 3 — enrich each project from its page, MERGED onto the API row.

Keeps the reliable list-API fields (country, sector, date, amount) and adds:
  SUMMARY SHEET tab:  status, promoter, proposed_eib_finance, total_cost,
                      objectives / environmental_aspects / procurement, PDF links
  SIGNATURE(S) tab:   total_signed_eur, the per-tranche signature timeline
                      (date : amount), and the per-country / per-sector breakdowns

The signature timeline matters: a project can be signed in several tranches across
different years (e.g. 2022 + a 2026 top-up), so one signature_date understates it.
Per-tranche rows are written to a long table: data/interim/signatures_<country>.csv

Money is also parsed to numeric *_eur columns, and CSVs are written UTF-8-with-BOM
so Excel shows the € correctly.
"""
from __future__ import annotations
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
from bs4 import BeautifulSoup

PDF_RE = re.compile(r"\.pdf($|\?)", re.I)
STATUS_RE = re.compile(r"\b(Signed|Approved|Under appraisal|Dropped)\s*\|\s*(\d{2}/\d{2}/\d{4})")
EUR_RE = re.compile(r"EUR\s*[\d.,]+\s*(?:million|billion|m|bn)?", re.I)
SIG_RE = re.compile(r"^(\d{2}/\d{2}/\d{4})\s*:\s*€?\s*([\d.,]+)")
SECTIONS = ["Objectives", "Environmental aspects", "Procurement", "Technical description"]


def _sigkey(d):
    """Sort key for a dd/mm/yyyy date string -> yyyymmdd."""
    return d[-4:] + d[3:5] + d[:2]


def _eur_plain(s):
    s = str(s).replace(",", "")
    m = re.findall(r"[0-9]+(?:\.[0-9]+)?", s)
    return float(m[0]) if m else np.nan


def _eur_words(s):
    m = re.search(r"([\d.]+)\s*(billion|bn|million|m)?", str(s), re.I)
    if not m:
        return np.nan
    v = float(m.group(1)); u = (m.group(2) or "").lower()
    return v * 1e9 if u in ("billion", "bn") else v * 1e6 if u in ("million", "m") else v


def _countries(soup):
    names, codes = [], []
    for a in soup.select('a[href*="countries="]'):
        code = re.search(r"countries=([A-Za-z]{2})", a["href"])
        nm = a.get_text(" ", strip=True)
        if nm:
            names.append(nm)
        if code:
            codes.append(code.group(1).upper())
    return list(dict.fromkeys(names)), list(dict.fromkeys(codes))


def _split_description(text):
    out = {"objectives": None, "environmental_aspects": None,
           "procurement": None, "technical_description": None}
    key = {"Objectives": "objectives", "Environmental aspects": "environmental_aspects",
           "Procurement": "procurement", "Technical description": "technical_description"}
    pat = re.compile(r"(" + "|".join(re.escape(h) for h in SECTIONS) + r")")
    parts = pat.split(text)
    for i in range(1, len(parts) - 1, 2):
        h, body = parts[i].strip(), parts[i + 1].strip()
        if h in key and body:
            out[key[h]] = body[:2000]
    return out


def _promoter(text, title):
    idx = text.find("Promoter")
    if idx == -1:
        return None
    for ln in (l.strip() for l in text[idx:].split("\n")[1:]):
        if not ln or ln in ("Project name",):
            continue
        if title and ln.strip() == str(title).strip():
            continue
        return ln
    return None


def parse_signatures(text):
    """Parse the SIGNATURE(S) tab into the per-tranche timeline (date : amount).

    Every tranche is kept, in chronological order, and also summed to
    total_signed_eur. The full list of dates/amounts is surfaced on the panel
    (signature_dates / signature_amounts) as well as in the long table.
    """
    sigs = []
    for ln in (l.strip() for l in text.splitlines() if l.strip()):
        m = SIG_RE.match(ln)
        if m:
            sigs.append((m.group(1), _eur_plain(m.group(2))))
    sigs.sort(key=lambda da: _sigkey(da[0]))
    years = sorted({d[-4:] for d, _ in sigs})
    return {
        "signatures": sigs,
        "total_signed_eur": float(np.nansum([a for _, a in sigs])) if sigs else np.nan,
        "n_signatures": len(sigs),
        "first_signature": sigs[0][0] if sigs else None,
        "last_signature": sigs[-1][0] if sigs else None,
        "signature_dates": ";".join(d for d, _ in sigs),
        "signature_amounts": ";".join("" if a != a else f"{a:.0f}" for _, a in sigs),
        "signature_years": ";".join(years),
    }


def parse_project(html, title=None):
    soup = BeautifulSoup(html, "lxml")
    main = soup.find("main") or soup
    text = main.get_text("\n", strip=True)
    rec = {}

    m = STATUS_RE.search(text)
    rec["status"] = m.group(1) if m else None
    rec["signed_date_page"] = m.group(2) if m else None

    names, codes = _countries(soup)
    rec["location_countries"] = "; ".join(names)
    rec["location_country_codes"] = "; ".join(codes)

    # summary-sheet amounts (EUR-prefixed, before the Description block)
    flat = main.get_text(" ", strip=True)
    cut = min([p for p in (flat.find("Description"), flat.find("Objectives")) if p != -1] or [len(flat)])
    amts = [re.sub(r"\s+", " ", a.strip()) for a in EUR_RE.findall(flat[:cut])]
    rec["proposed_eib_finance"] = amts[0] if len(amts) >= 1 else None
    rec["total_cost"] = amts[1] if len(amts) >= 2 else None
    rec["proposed_eib_eur"] = _eur_words(rec["proposed_eib_finance"])
    rec["total_cost_eur"] = _eur_words(rec["total_cost"])

    rec["promoter"] = _promoter(text, title)
    rec.update(_split_description(text))
    rec["description_full"] = text[:6000]

    # SIGNATURE(S) tab
    rec.update(parse_signatures(text))

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

    records, sig_rows = [], []
    for _, idrow in ids.iterrows():
        pid, url = str(idrow["project_id"]), idrow["url"]
        html = fetcher.get_text(url)
        enrich = parse_project(html, title=idrow.get("title"))
        sigs = enrich.pop("signatures", [])
        for d, a in sigs:
            sig_rows.append({"project_id": pid, "signature_date": d, "amount_eur": a})
        merged = {**idrow.to_dict(), **enrich}
        merged["amount_eur"] = _eur_plain(merged.get("amount_text"))
        (cache / f"{pid}.json").write_text(json.dumps({**merged, "documents": enrich.get("documents", [])},
                                                      ensure_ascii=False, default=str), encoding="utf-8")
        records.append(merged)

    df = pd.DataFrame(records).drop(columns=["documents"], errors="ignore")
    # sanity / analysis ratios
    with np.errstate(divide="ignore", invalid="ignore"):
        df["signed_vs_proposed"] = (df["total_signed_eur"] / df["proposed_eib_eur"]).round(2)
        df["eib_share_of_cost"] = (df["total_signed_eur"] / df["total_cost_eur"]).round(3)
    df = df.replace([np.inf, -np.inf], np.nan)
    out = ids_csv.parent / ids_csv.name.replace("ids_", "pages_")
    df.to_csv(out, index=False, encoding="utf-8-sig")
    sig_out = ids_csv.parent / f"signatures_{cfg['slice']['country'].lower()}.csv"
    pd.DataFrame(sig_rows).to_csv(sig_out, index=False, encoding="utf-8-sig")
    print(f"[fetch_pages] enriched {len(df)} projects ({df['n_pdfs'].sum()} PDFs; "
          f"{len(sig_rows)} signature tranches -> {sig_out.name})")
    return out
