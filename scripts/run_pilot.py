#!/usr/bin/env python3
"""Run the EIB scraper pilot end to end on the configured slice (stages 1-4).

    python scripts/run_pilot.py [config/pilot.yaml]

The enriched pages file IS the panel (list-API fields + page enrichment + signature
timeline). Completeness is verified separately by scripts/build_cas.py (CAS green
cross-check). Stages 5 (classify) and 6 (geocode) are stubs.
"""
from __future__ import annotations
import shutil
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from eibscraper import harvest_ids, fetch_pages, fetch_pdfs   # noqa: E402
from eibscraper.utils import Fetcher                           # noqa: E402


def main(cfg_path: str) -> None:
    cfg = yaml.safe_load(Path(cfg_path).read_text(encoding="utf-8"))
    f = cfg["fetch"]
    fetcher = Fetcher(cache_dir=f["cache_dir"], contact=f["contact"],
                      min_delay=f["min_delay_seconds"], max_retries=f["max_retries"])

    print(f"=== PILOT: {cfg['slice']['country']} {cfg['slice']['years']} ===")
    ids_csv = harvest_ids.run(cfg, fetcher)              # 1. list API -> project IDs + core fields
    pages_csv = fetch_pages.run(cfg, fetcher, ids_csv)   # 3. pages -> enrichment + signatures
    fetch_pdfs.run(cfg, fetcher)                         # 4. PDFs -> text + location cues (+failure log)

    panel = Path("data/processed") / f"pilot_projects_{cfg['slice']['country'].lower()}.csv"
    panel.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(pages_csv, panel)
    print(f"\nPanel -> {panel}")
    print("\n=== DONE ===")
    print("Next: run scripts/build_cas.py for green tags + completeness, "
          "then wire classify.py / geocode.py.")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "config/pilot.yaml")
