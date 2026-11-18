"""Stage 4 — download the ESDS/NTS PDF per project, extract text with a fallback
reader chain, and LOG any PDF no reader could parse so you can retrieve it by hand.

Reader order: pdfplumber -> pypdf -> pdftotext (poppler, if installed).
Outputs:
    data/interim/pdf_text/<project_id>.txt     extracted text
    data/interim/pdf_locations_<country>.csv   candidate location cues (+ which reader)
    data/interim/pdf_failures.csv              project_id, project_url, doc, pdf_url, reason
"""
from __future__ import annotations
import json
import re
import shutil
import subprocess
from pathlib import Path

import pandas as pd

PRIORITY = re.compile(r"(environmental|social|data sheet|ESDS|non.technical|NTS)", re.I)
LOC_CUES = re.compile(r"(\d+\s?km\s+(?:north|south|east|west|from|of)[^.]{0,60}"
                      r"|near\s+[A-Z][a-z]+[^.]{0,40}"
                      r"|located\s+in\s+[A-Z][a-z]+[^.]{0,40})", re.I)


def _read_pdfplumber(path: Path, max_pages: int = 15) -> str:
    import pdfplumber
    out = []
    with pdfplumber.open(path) as pdf:
        for pg in pdf.pages[:max_pages]:
            out.append(pg.extract_text() or "")
    return "\n".join(out)


def _read_pypdf(path: Path, max_pages: int = 15) -> str:
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    out = []
    for pg in reader.pages[:max_pages]:
        out.append(pg.extract_text() or "")
    return "\n".join(out)


def _read_pdftotext(path: Path, max_pages: int = 15) -> str:
    if not shutil.which("pdftotext"):
        raise RuntimeError("pdftotext (poppler) not installed")
    r = subprocess.run(["pdftotext", "-f", "1", "-l", str(max_pages), str(path), "-"],
                       capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or "pdftotext failed").strip()[:120])
    return r.stdout


READERS = [("pdfplumber", _read_pdfplumber), ("pypdf", _read_pypdf), ("pdftotext", _read_pdftotext)]


def extract_text(path: Path) -> tuple[str, str]:
    """Try each reader in order; return (text, reader_name). Raise if all fail/empty."""
    errors = []
    for name, fn in READERS:
        try:
            t = fn(path)
            if t and t.strip():
                return t, name
            errors.append(f"{name}: empty")
        except Exception as e:  # noqa: BLE001
            errors.append(f"{name}: {type(e).__name__}")
    raise RuntimeError("; ".join(errors))


def run(cfg, fetcher, pages_json_dir: str = "data/interim/pages_json") -> Path:
    pages_dir = Path(pages_json_dir)
    txt_dir = Path("data/interim/pdf_text")
    txt_dir.mkdir(parents=True, exist_ok=True)

    rows, failures = [], []
    for jf in sorted(pages_dir.glob("*.json")):
        rec = json.loads(jf.read_text(encoding="utf-8"))
        pid, url = rec.get("project_id"), rec.get("url")
        docs = rec.get("documents", []) or []
        chosen = next((d for d in docs if PRIORITY.search(d["label"])), docs[0] if docs else None)
        if not chosen:
            continue
        try:
            pdf_path = fetcher.get_pdf(chosen["href"])
        except Exception as e:  # noqa: BLE001
            failures.append({"project_id": pid, "project_url": url, "doc_label": chosen["label"],
                             "pdf_url": chosen["href"], "reason": f"download: {type(e).__name__}"})
            continue
        try:
            text, reader = extract_text(pdf_path)
        except Exception as e:  # noqa: BLE001 — all readers failed; record for manual retrieval
            failures.append({"project_id": pid, "project_url": url, "doc_label": chosen["label"],
                             "pdf_url": chosen["href"], "reason": str(e)[:200]})
            continue
        (txt_dir / f"{pid}.txt").write_text(text, encoding="utf-8")
        cues = list({m.group(0).strip() for m in LOC_CUES.finditer(text)})[:5]
        rows.append({"project_id": pid, "doc_label": chosen["label"], "reader": reader,
                     "text_chars": len(text), "location_cues": " | ".join(cues)})

    out = Path("data/interim") / f"pdf_locations_{cfg['slice']['country'].lower()}.csv"
    pd.DataFrame(rows).to_csv(out, index=False)
    fail_csv = Path("data/interim") / "pdf_failures.csv"
    pd.DataFrame(failures).to_csv(fail_csv, index=False)
    print(f"[fetch_pdfs] extracted {len(rows)} PDFs; {len(failures)} failed "
          f"(logged -> {fail_csv}) -> {out}")
    return out