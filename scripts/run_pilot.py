#!/usr/bin/env python3
"""Run the EIB scraper pilot end to end on the configured slice (stages 1-4).

    python scripts/run_pilot.py [config/pilot.yaml]

The enriched pages file IS the panel (list-API fields + page enrichment). The join to
the manually-downloaded spine export is an OPTIONAL cross-check and never fatal — it is
skipped cleanly if loanExport.xlsx is missing or unreadable (e.g. OneDrive timeouts).
Stages 5 (classify) and 6 (geocode) are stubs.
"""
from __future__ import annotations
import shutil
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from eibscraper import harvest_ids, fetch_pages, fetch_pdfs, join_spine   # noqa: E402
from eibscraper.utils import Fetcher                                       # noqa: E402


def main(cfg_path: str) -> None:
    cfg = yaml.safe_load(Path(cfg_path).read_text(encoding="utf-8"))
    f = cfg["fetch"]
    fetcher = Fetcher(cache_dir=f["cache_dir"], contact=f["contact"],
                      min_delay=f["min_delay_seconds"], max_retries=f["max_retries"])

    print(f"=== PILOT: {cfg['slice']['country']} {cfg['slice']['years']} ===")
    ids_csv = harvest_ids.run(cfg, fetcher)              # 1. list API -> project IDs + core fields
    pages_csv = fetch_pages.run(cfg, fetcher, ids_csv)   # 3. pages -> enrichment (merged)
    fetch_pdfs.run(cfg, fetcher)                         # 4. PDFs -> text + location cues

    # the enriched pages file is the panel
    panel = Path("data/processed") / f"pilot_projects_{cfg['slice']['country'].lower()}.csv"
    panel.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(pages_csv, panel)
    print(f"\nPanel -> {panel}")

    # optional cross-check against the manual spine export (never fatal)
    try:
        join_spine.run(cfg, pages_csv)
    except Exception as e:  # noqa: BLE001
        print(f"[join_spine] optional cross-check skipped: {type(e).__name__}: {e}")

    print("\n=== DONE ===")
    print("Next: inspect the panel + PDF location cues, then wire classify.py / geocode.py.")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "config/pilot.yaml")
