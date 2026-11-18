"""Consolidate the EIB Climate Action & Sustainability (CAS) detailed lists into one
project-level GREEN BENCHMARK, and join it to a scraped panel.

Project-level CAS detail exists from 2021 onward:
  - xlsx  : 2023/2024/2025 (detailed-list sheet; sheet name & header row auto-detected)
  - pdf   : 2021/2022 ("... lending by project" tables)
Pre-2021 CAS files are country-aggregate tables (different structure) and are skipped —
their project-level green status has to be inferred later (backward induction from the
2021–2025 labelled matches).

Column names vary by year; we normalise to a common schema. Note "Green Finance %"
(2025 wording) == "Climate Action & Environmental Sustainability %" (2021–2024) — the
CA&ES green share. We keep that as `caes_pct`, plus `climate_action_pct` and
`env_sust_pct` separately.

Usage:
    python scripts/build_cas.py                      # build benchmark + join to the pilot panel
    # or programmatically:
    from eibscraper import cas_append
    bench = cas_append.build_benchmark("data/raw")
    cas_append.match_panel("data/processed/pilot_projects_ireland.csv", bench)
"""
from __future__ import annotations
import glob
import re
from pathlib import Path

import pandas as pd

try:
    import pdfplumber
except Exception:  # noqa: BLE001
    pdfplumber = None

# canonical schema
CANON = ["year", "signature_date", "country", "financing_type", "operation_name",
         "operation_description", "amount_eurm", "caes_pct", "caes_eurm",
         "env_sust_pct", "env_sust_eurm", "climate_action_pct", "climate_action_eurm",
         "source_file"]


def _norm(s) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(s).upper())


def _flat(c) -> str:
    return re.sub(r"\s+", " ", str(c or "").replace("\n", " ")).strip()


def _pct(x):
    """Normalise a share to a 0–1 fraction. PDFs give '100.%' (0–100 + sign);
    xlsx give 0–1 fractions. Presence of '%' means a 0–100 value."""
    import numpy as np
    s = str(x).strip()
    if s in ("", "nan", "None", "<NA>"):
        return np.nan
    if "%" in s:
        v = re.sub(r"[^0-9.]", "", s)
        return float(v) / 100 if v not in ("", ".") else np.nan
    try:
        return float(s)
    except ValueError:
        return np.nan


def _num(x):
    import numpy as np
    s = re.sub(r"[^0-9.\-]", "", str(x))
    try:
        return float(s) if s not in ("", ".", "-") else np.nan
    except ValueError:
        return np.nan


def _map_columns(cols: list[str]) -> dict:
    """Map messy/variant headers to canonical names by content."""
    m = {}
    for c in cols:
        f = _flat(c).lower()
        if "operation name" in f: m[c] = "operation_name"
        elif "operation description" in f: m[c] = "operation_description"
        elif "country name" in f: m[c] = "country"
        elif "signature" in f or (f.startswith("contract") and "date" in f): m[c] = "signature_date"
        elif "financing" in f and "type" in f: m[c] = "financing_type"
        elif "amount signed" in f: m[c] = "amount_eurm"
        # green share (CA&ES / Green Finance) — check BEFORE plain climate action
        elif ("green finance" in f or ("climate action" in f and ("environmental" in f or "envio" in f or "enviro" in f))):
            m[c] = "caes_eurm" if ("eurm" in f or "meur" in f or "(eur" in f) else "caes_pct"
        elif "environmental sustainab" in f or "enviro. sustainab" in f or "envio. sustainab" in f:
            m[c] = "env_sust_eurm" if ("eurm" in f or "meur" in f) else "env_sust_pct"
        elif "climate action" in f:
            m[c] = "climate_action_eurm" if ("eurm" in f or "meur" in f) else "climate_action_pct"
    return m


def _finalise(df: pd.DataFrame, year: int, src: str) -> pd.DataFrame:
    df = df.rename(columns=_map_columns(list(df.columns)))
    for col in CANON:
        if col not in df.columns:
            df[col] = pd.NA
    df = df[df["operation_name"].notna() & (df["operation_name"].astype(str).str.len() > 2)]
    for c in ["caes_pct", "env_sust_pct", "climate_action_pct"]:
        df[c] = df[c].map(_pct)
    for c in ["amount_eurm", "caes_eurm", "env_sust_eurm", "climate_action_eurm"]:
        df[c] = df[c].map(_num)
    df["source_file"] = src
    # year: prefer parsed signature date, else the file's year
    sd = pd.to_datetime(df["signature_date"], errors="coerce", dayfirst=True)
    df["year"] = sd.dt.year.fillna(year).astype(int)
    df["signature_date"] = sd.dt.date.astype(str)
    return df[CANON]


# ---------------------------------------------------------------- xlsx
def load_xlsx(path: str) -> pd.DataFrame | None:
    xl = pd.ExcelFile(path)
    sheet = next((s for s in xl.sheet_names if "detailed" in s.lower()), None)
    if not sheet:
        return None
    raw = pd.read_excel(path, sheet_name=sheet, header=None, nrows=10)
    hdr = next((i for i, r in raw.iterrows()
                if r.astype(str).str.contains("Operation Name", case=False).any()), None)
    if hdr is None:
        return None
    df = pd.read_excel(path, sheet_name=sheet, header=hdr).dropna(how="all")
    df.columns = [_flat(c) for c in df.columns]
    return _finalise(df, year=0, src=Path(path).name)


# ---------------------------------------------------------------- pdf
def load_pdf(path: str) -> pd.DataFrame | None:
    if pdfplumber is None:
        print(f"[cas_append] pdfplumber missing; cannot read {path}")
        return None
    with pdfplumber.open(path) as pdf:
        head = (pdf.pages[0].extract_text() or "").lower()
        yr_m = re.search(r"20\d{2}", head)
        year = int(yr_m.group()) if yr_m else 0
        # project-level detection: look for an "Operation Name" table header in the
        # first few pages (title wording varies, so don't rely on "by project").
        probe = False
        for p in pdf.pages[:12]:
            for t in (p.extract_tables() or []):
                if any(any("Operation Name" in _flat(c) for c in (row or [])) for row in t):
                    probe = True; break
            if probe:
                break
        if not probe:
            return None  # aggregate (country-level) file, skip
        header_map, rows = None, []
        for p in pdf.pages:
            for t in (p.extract_tables() or []):
                for row in t:
                    if not row:
                        continue
                    cells = [_flat(c) for c in row]
                    if header_map is None:
                        if any("Operation Name" in c for c in cells):
                            header_map = {i: c for i, c in enumerate(cells)}
                        continue
                    # data row
                    rows.append(cells)
    if header_map is None:
        return None
    ncol = max(len(r) for r in rows) if rows else 0
    cols = [header_map.get(i, f"col{i}") for i in range(ncol)]
    df = pd.DataFrame([r + [None] * (ncol - len(r)) for r in rows], columns=cols)
    return _finalise(df, year=year, src=Path(path).name)


# ---------------------------------------------------------------- build + match
def build_benchmark(raw_dir: str = "data/raw", write_to: str = "data/interim/cas_benchmark.csv") -> pd.DataFrame:
    frames, xlsx_years = [], set()
    for x in sorted(glob.glob(str(Path(raw_dir) / "*.xlsx"))):
        d = load_xlsx(x)
        if d is not None and len(d):
            frames.append(d); xlsx_years |= set(d.year.unique())
            print(f"[cas_append] xlsx {Path(x).name}: {len(d)} rows, years {sorted(d.year.unique())}")
    for pdf in sorted(glob.glob(str(Path(raw_dir) / "*.pdf"))):
        d = load_pdf(pdf)
        if d is None or not len(d):
            continue
        # prefer the cleaner xlsx when a year is covered by both
        if set(d.year.unique()) & xlsx_years:
            print(f"[cas_append] pdf  {Path(pdf).name}: skipped (year {sorted(d.year.unique())} already from xlsx)")
            continue
        frames.append(d); print(f"[cas_append] pdf  {Path(pdf).name}: {len(d)} rows, year {sorted(d.year.unique())}")
    if not frames:
        raise RuntimeError(f"No project-level CAS files found in {raw_dir}")
    allrows = pd.concat(frames, ignore_index=True)
    # aggregate tranches -> one row per operation (sum EURM; pct is constant per op)
    for c in ["amount_eurm", "caes_eurm", "env_sust_eurm", "climate_action_eurm"]:
        allrows[c] = pd.to_numeric(allrows[c], errors="coerce")
    for c in ["caes_pct", "env_sust_pct", "climate_action_pct"]:
        allrows[c] = pd.to_numeric(allrows[c], errors="coerce")
    g = (allrows.groupby(["year", "country", "operation_name"], as_index=False)
         .agg(signature_date=("signature_date", "first"),
              financing_type=("financing_type", "first"),
              amount_eurm=("amount_eurm", "sum"),
              caes_pct=("caes_pct", "max"), caes_eurm=("caes_eurm", "sum"),
              env_sust_pct=("env_sust_pct", "max"),
              climate_action_pct=("climate_action_pct", "max"),
              source_file=("source_file", "first")))
    g["name_key"] = g["operation_name"].map(_norm)
    Path(write_to).parent.mkdir(parents=True, exist_ok=True)
    g.to_csv(write_to, index=False)
    print(f"[cas_append] benchmark: {len(g)} operations, {g.year.min()}-{g.year.max()} -> {write_to}")
    return g


def match_panel(panel_csv: str, bench: pd.DataFrame, score: int = 88,
                write_to: str | None = None) -> pd.DataFrame:
    from rapidfuzz import process, fuzz
    panel = pd.read_csv(panel_csv)
    panel["year"] = pd.to_datetime(panel["signature_date"], errors="coerce").dt.year
    panel["name_key"] = panel["title"].map(_norm)

    attach = []
    for _, r in panel.iterrows():
        pool = bench[bench.year == r["year"]]
        best = (process.extractOne(r["name_key"], pool["name_key"].tolist(),
                                   scorer=fuzz.token_sort_ratio) if len(pool) else None)
        if best and best[1] >= score:
            b = pool.iloc[best[2]]
            attach.append({"cas_matched": True, "caes_pct": b["caes_pct"],
                           "climate_action_pct": b["climate_action_pct"],
                           "cas_amount_eurm": b["amount_eurm"], "cas_caes_eurm": b["caes_eurm"],
                           "cas_operation": b["operation_name"], "cas_year": b["year"]})
        else:
            attach.append({"cas_matched": False, "caes_pct": pd.NA,
                           "climate_action_pct": pd.NA, "cas_amount_eurm": pd.NA,
                           "cas_caes_eurm": pd.NA, "cas_operation": pd.NA, "cas_year": pd.NA})
    out = pd.concat([panel.reset_index(drop=True), pd.DataFrame(attach)], axis=1)
    if write_to:
        out.to_csv(write_to, index=False)
    print(f"[cas_append] panel matched to CAS: {out['cas_matched'].sum()}/{len(out)} "
          f"carry an official green tag")
    return out


def reconcile_amounts(panel_csv: str, sig_csv: str, bench: pd.DataFrame, country: str,
                      score: int = 88, tol_eurm: float = 0.5,
                      write_to: str | None = None) -> pd.DataFrame:
    """Reconcile SCRAPED signed amounts against the CAS annual amounts, per year.

    CAS lists are annual and in EUR millions; the benchmark already sums any
    within-year tranches into one figure per (operation, year). The scrape's
    per-tranche long table gives every signature date + amount (raw EUR). So we
    line them up per (project, year):

        scrape_eurm = sum of that project's scraped tranche amounts in year Y / 1e6
        cas_eurm    = CAS amount_eurm for the matched operation in year Y

    A project signed twice in 2022 shows n_tranches=2 against one CAS 2022 figure;
    a project signed in 2022 and 2026 produces two rows. diff_eurm flags anything
    that does not line up within tol_eurm.
    """
    import numpy as np
    from rapidfuzz import process, fuzz

    panel = pd.read_csv(panel_csv)
    panel["name_key"] = panel["title"].map(_norm)
    sigs = pd.read_csv(sig_csv)
    sigs["year"] = pd.to_datetime(sigs["signature_date"], errors="coerce", dayfirst=True).dt.year
    scrape_py = (sigs.groupby(["project_id", "year"])
                 .agg(scrape_eurm=("amount_eur", lambda s: float(s.sum()) / 1e6),
                      n_tranches=("amount_eur", "size")).reset_index())

    cas = bench[bench.country.str.contains(country, case=False, na=False)].copy()
    rows = []
    for _, r in panel.iterrows():
        best = (process.extractOne(r["name_key"], cas["name_key"].tolist(),
                                   scorer=fuzz.token_sort_ratio) if len(cas) else None)
        if not best or best[1] < score:
            continue
        op = cas.iloc[best[2]]["operation_name"]
        cas_op = cas[cas["operation_name"] == op][["year", "amount_eurm"]]
        mine = scrape_py[scrape_py["project_id"].astype(str) == str(r.get("project_id"))]
        years = sorted(set(cas_op["year"].dropna().astype(int))
                       | set(mine["year"].dropna().astype(int)))
        for y in years:
            s = mine[mine["year"] == y]
            c = cas_op[cas_op["year"] == y]
            s_amt = float(s["scrape_eurm"].sum()) if len(s) else np.nan
            c_amt = float(c["amount_eurm"].sum()) if len(c) else np.nan
            rows.append({
                "project_id": r.get("project_id"), "title": str(r["title"])[:50],
                "cas_operation": op, "year": y,
                "scrape_eurm": round(s_amt, 3) if s_amt == s_amt else np.nan,
                "n_tranches": int(s["n_tranches"].sum()) if len(s) else 0,
                "cas_eurm": round(c_amt, 3) if c_amt == c_amt else np.nan,
                "diff_eurm": round((0 if s_amt != s_amt else s_amt)
                                   - (0 if c_amt != c_amt else c_amt), 3),
            })
    rec = pd.DataFrame(rows)
    if len(rec):
        both = rec["scrape_eurm"].notna() & rec["cas_eurm"].notna()
        rec["reconciles"] = both & (rec["diff_eurm"].abs() <= tol_eurm)
        print(f"[reconcile] {int(rec['reconciles'].sum())}/{int(both.sum())} "
              f"project-years with both figures reconcile within €{tol_eurm}m "
              f"({len(rec)} project-years total)")
        for _, x in rec[both & ~rec["reconciles"]].iterrows():
            print(f"    MISMATCH [{x['year']}] {x['title']}: scrape €{x['scrape_eurm']}m "
                  f"({x['n_tranches']} tranche(s)) vs CAS €{x['cas_eurm']}m")
        only_scrape = rec["cas_eurm"].isna().sum()
        only_cas = rec["scrape_eurm"].isna().sum()
        if only_scrape or only_cas:
            print(f"    (year present in scrape only: {only_scrape}; in CAS only: {only_cas})")
    else:
        print("[reconcile] no matched operations to reconcile")
    if write_to:
        Path(write_to).parent.mkdir(parents=True, exist_ok=True)
        rec.to_csv(write_to, index=False)
    return rec


def completeness_check(panel_csv: str, bench: pd.DataFrame, country: str, score: int = 88):
    """Every CAS green op in `country` for the panel's years should be IN the panel."""
    from rapidfuzz import process, fuzz
    panel = pd.read_csv(panel_csv)
    panel["year"] = pd.to_datetime(panel["signature_date"], errors="coerce").dt.year
    panel["name_key"] = panel["title"].map(_norm)
    yrs = set(panel["year"].dropna().astype(int))
    cas_ie = bench[(bench.country.str.contains(country, case=False, na=False)) & (bench.year.isin(yrs))]
    missing = []
    for _, r in cas_ie.iterrows():
        pool = panel[panel.year == r["year"]]
        best = (process.extractOne(r["name_key"], pool["name_key"].tolist(),
                                   scorer=fuzz.token_sort_ratio) if len(pool) else None)
        if not best or best[1] < score:
            missing.append((r["year"], r["operation_name"]))
    print(f"[cas_append] completeness for {country}: {len(cas_ie)} CAS green ops in panel years; "
          f"{len(missing)} NOT found in scrape")
    for y, n in missing:
        print(f"    MISSING [{y}] {n}")
    return missing


if __name__ == "__main__":
    b = build_benchmark("data/raw")
    match_panel("data/processed/pilot_projects_ireland.csv", b,
                write_to="data/processed/pilot_projects_ireland_cas.csv")
    completeness_check("data/processed/pilot_projects_ireland.csv", b, "Ireland")
    reconcile_amounts("data/processed/pilot_projects_ireland.csv",
                      "data/interim/signatures_ireland.csv", b, "Ireland",
                      write_to="data/interim/cas_reconciliation_ireland.csv")
