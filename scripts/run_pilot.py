#!/usr/bin/env python3
"""Run the EIB scraper pilot end to end on the configured slice (stages 1-4).

    python scripts/run_pilot.py [config/pilot.yaml]

Stages 5 (classify) and 6 (geocode) are stubs — the pilot stops at a tidy
project panel plus candidate location cues, which is enough to prove the pipeline.
"""
from __future__ import annotations
import sys
from pathlib import Path

import yaml

# make src/ importable without installing
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from eibscraper import harvest_ids, fetch_pages, fetch_pdfs, join_spine   # noqa: E402
from eibscraper.utils import Fetcher                                       # noqa: E402


def main(cfg_path: str) -> None:
    cfg = yaml.safe_load(Path(cfg_path).read_text(encoding="utf-8"))
    f = cfg["fetch"]
    fetcher = Fetcher(cache_dir=f["cache_dir"], contact=f["contact"],
                      min_delay=f["min_delay_seconds"], max_retries=f["max_retries"])

    print(f"=== PILOT: {cfg['slice']['country']} {cfg['slice']['years']} ===")
    ids_csv = harvest_ids.run(cfg, fetcher)          # 1. listing -> project IDs
    pages_csv = fetch_pages.run(cfg, fetcher, ids_csv)  # 3. pages -> fields + PDF links
    fetch_pdfs.run(cfg, fetcher)                      # 4. PDFs -> text + location cues
    panel = join_spine.run(cfg, pages_csv)           # 2/7. join to spine -> tidy panel

    print("\n=== DONE ===")
    print(f"Tidy pilot panel: {panel}")
    print("Next: inspect the panel + location cues, then wire in classify.py / geocode.py.")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "config/pilot.yaml")
