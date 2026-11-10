"""Stage 4 — download the ESDS/NTS PDFs and extract text + candidate place names.

Prioritises environmental data sheets (ESDS) and non-technical summaries (NTS),
where sub-national location sits as free text. Real geocoding is stage 6; here we
just pull the text and surface candidate location strings for inspection.

Output: data/interim/pdf_text/<project_id>.txt  and  pdf_locations_<slice>.csv
"""
from __future__ import annotations
import json
import re
from pathlib import Path

import pandas as pd
import pdfplumber

# documents most likely to carry site detail
PRIORITY = re.compile(r"(environmental|social|data sheet|ESDS|non.technical|NTS)", re.I)
# crude candidate-location cues (replaced by a proper geocoder in stage 6)
LOC_CUES = re.compile(r"(\d+\s?km\s+(?:north|south|east|west|from|of)[^.]{0,60}"
                      r"|near\s+[A-Z][a-z]+[^.]{0,40}"
                      r"|located\s+in\s+[A-Z][a-z]+[^.]{0,40})", re.I)


def extract_text(pdf_path: Path, max_pages: int = 15) -> str:
    out = []
    with pdfplumber.open(pdf_path) as pdf:
        for pg in pdf.pages[:max_pages]:
            out.append(pg.extract_text() or "")
    return "\n".join(out)


def run(cfg, fetcher, pages_json_dir: str = "data/interim/pages_json") -> Path:
    pages_dir = Path(pages_json_dir)
    txt_dir = Path("data/interim/pdf_text")
    txt_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for jf in sorted(pages_dir.glob("*.json")):
        rec = json.loads(jf.read_text(encoding="utf-8"))
        pid = rec["project_id"]
        docs = rec.get("documents", [])
        # pick the priority doc (ESDS/NTS) if present, else the first PDF
        chosen = next((d for d in docs if PRIORITY.search(d["label"])), docs[0] if docs else None)
        if not chosen:
            continue
        pdf_path = fetcher.get_pdf(chosen["href"])
        try:
            text = extract_text(pdf_path)
        except Exception as e:  # noqa: BLE001 - keep the pilot moving, log the miss
            print(f"[fetch_pdfs] {pid}: PDF parse failed ({e})")
            continue
        (txt_dir / f"{pid}.txt").write_text(text, encoding="utf-8")
        cues = list({m.group(0).strip() for m in LOC_CUES.finditer(text)})[:5]
        rows.append({"project_id": pid, "doc_label": chosen["label"],
                     "text_chars": len(text), "location_cues": " | ".join(cues)})

    df = pd.DataFrame(rows)
    out = Path("data/interim") / f"pdf_locations_{cfg['slice']['country'].lower()}.csv"
    df.to_csv(out, index=False)
    print(f"[fetch_pdfs] extracted {len(df)} PDFs -> {out}")
    return out
