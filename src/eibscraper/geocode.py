"""Stage 6 — geography: place-name extraction -> coordinates / NUTS (NEXT PHASE — stub).

Design (see docs/):
  * Source text: project description + the ESDS/NTS PDF text (fetch_pdfs output).
  * Extract candidate place names (NER / LLM), then geocode (e.g. Nominatim/OSM,
      GISCO) to coordinates and map to NUTS3.
  * CRITICAL caveat (Ebeling): a place named in a description need not be the
      investment site, so every geocode must be manually validated on a sample;
      report the false-positive rate by product type.
  * Only the direct-loan / sited-asset subset is geocodable; intermediated loans
      are flagged as not-locatable.

Interface stub below; wire in the geocoder once the pilot text extraction is verified.
"""
from __future__ import annotations
import pandas as pd


def geocode_projects(df: pd.DataFrame) -> pd.DataFrame:
    """Return df with added columns: place_name, lat, lon, nuts3, geocode_confidence."""
    raise NotImplementedError(
        "Geocoding not yet wired in — see docstring. "
        "Pilot stops at candidate location cues from fetch_pdfs.")
