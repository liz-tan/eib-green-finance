"""Stage 5 — green / sector / intermediated classification (NEXT PHASE — stub).

Design (see docs/):
  * Input: operation name + description (from the spine), per project.
  * Model: an LLM reads each description and returns a structured tag set —
      green (bool/share), climate objective (mitigation sub-sector / adaptation),
      direct-vs-intermediated, technology.
  * Why LLM not keywords: green signal is sparse in raw keywords (~258 "green",
      508 "climate" of 22,931), so a dictionary misses most climate-relevant loans.
  * Validation: score against the EIB CAS "detailed list" green shares (2016-2025)
      as a labelled benchmark; report accuracy / Cohen's kappa on a held-out sample.
  * Reproducibility: version the prompt + the hand-labelled gold set in the repo.

Keep the interface stable so the pilot panel can be extended without reshaping.
"""
from __future__ import annotations
import pandas as pd


def classify_descriptions(df: pd.DataFrame, text_col: str = "desc") -> pd.DataFrame:
    """Return df with added columns: green_share, objective, intermediated, technology.

    STUB. First cut can be a cheap heuristic (sector == 'Credit lines' -> intermediated)
    before the LLM pass is wired in.
    """
    out = df.copy()
    # cheap placeholder flag so downstream code has the column; replace with LLM output
    out["intermediated_flag"] = out.get("spine_sector", "").astype(str).str.contains(
        "Credit line", case=False, na=False)
    out["green_share"] = pd.NA
    out["objective"] = pd.NA
    out["technology"] = pd.NA
    raise NotImplementedError(
        "LLM classification not yet wired in — see docstring. "
        "Remove this line to run the placeholder heuristic only.")
