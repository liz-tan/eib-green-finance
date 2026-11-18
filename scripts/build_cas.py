#!/usr/bin/env python3
"""Build the CAS green benchmark and join it to a panel.

    python scripts/build_cas.py                 # uses the Ireland pilot panel
    python scripts/build_cas.py <panel.csv> <country>

Outputs:
    data/interim/cas_benchmark.csv              # consolidated project-level CAS (2018-2025)
    <panel>_cas.csv                             # panel + official green % per project
and prints the completeness check (every CAS green op in <country> for the panel's
years must appear in the panel; any that don't are scrape gaps).
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from eibscraper import cas_append   # noqa: E402


def main(panel: str, country: str) -> None:
    bench = cas_append.build_benchmark("data/raw")
    out = panel.replace(".csv", "_cas.csv")
    cas_append.match_panel(panel, bench, write_to=out)
    cas_append.completeness_check(panel, bench, country)
    sig_csv = f"data/interim/signatures_{country.lower()}.csv"
    recon = panel.replace(".csv", "_reconciliation.csv").replace("processed", "interim")
    cas_append.reconcile_amounts(panel, sig_csv, bench, country, write_to=recon)
    print(f"\nPanel with green % -> {out}")
    print(f"Amount reconciliation -> {recon}")


if __name__ == "__main__":
    p = sys.argv[1] if len(sys.argv) > 1 else "data/processed/pilot_projects_ireland.csv"
    c = sys.argv[2] if len(sys.argv) > 2 else "Ireland"
    main(p, c)
