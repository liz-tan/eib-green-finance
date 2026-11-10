"""Stage 2/7 — join harvested IDs + parsed pages back to the spine (portal export).

The export has no project ID, so we match on name + signature date + country +
amount. Name matching is fuzzy (rapidfuzz) to absorb minor formatting differences;
date + country + rounded-amount act as blocking keys to keep matches unique.

Output: data/processed/pilot_projects_<slice>.csv  (the tidy pilot panel)
"""
from __future__ import annotations
from pathlib import Path

import pandas as pd
from rapidfuzz import process, fuzz


def _norm(s) -> str:
    return "".join(ch for ch in str(s).upper() if ch.isalnum() or ch == " ").strip()


def load_spine(path: str, country: str, years: list[int]) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name="Loans")
    df.columns = ["name", "region", "country", "sector", "sigdate", "amount", "desc"]
    df["sigdate"] = pd.to_datetime(df["sigdate"], dayfirst=True, errors="coerce")
    df = df[(df["country"].str.contains(country, case=False, na=False)) &
            (df["sigdate"].dt.year.isin(years))].copy()
    df["name_key"] = df["name"].map(_norm)
    return df.reset_index(drop=True)


def run(cfg, pages_csv: Path) -> Path:
    s = cfg["slice"]
    spine = load_spine(cfg["paths"]["spine_export"], s["country"], s["years"])
    pages = pd.read_csv(pages_csv, dtype={"project_id": str})
    pages["name_key"] = pages["title"].map(_norm)

    # fuzzy match each scraped page to a spine row by name
    choices = spine["name_key"].tolist()
    matches = []
    for _, p in pages.iterrows():
        if not choices:
            break
        best = process.extractOne(p["name_key"], choices, scorer=fuzz.token_sort_ratio)
        if best and best[1] >= 85:          # score threshold — inspect borderline cases
            srow = spine.iloc[best[2]]
            matches.append({**p.to_dict(),
                            "spine_name": srow["name"],
                            "spine_sector": srow["sector"],
                            "spine_sigdate": srow["sigdate"],
                            "spine_amount": srow["amount"],
                            "match_score": best[1]})
    out_df = pd.DataFrame(matches)
    out = Path("data/processed") / f"pilot_projects_{s['country'].lower()}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(out, index=False)
    print(f"[join_spine] matched {len(out_df)}/{len(pages)} pages to spine "
          f"(>=85 score) -> {out}")
    return out
