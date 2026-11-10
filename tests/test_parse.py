"""Minimal parser tests — run: pytest -q"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from eibscraper.fetch_pages import parse_project, PDF_RE   # noqa: E402
from eibscraper.join_spine import _norm                    # noqa: E402

SAMPLE = """
<html><body><main>
  <h1>WEST OF DUDDON SANDS OFFSHORE WINDFARM</h1>
  <p>The project concerns a windfarm 14 km southwest of Barrow-in-Furness.</p>
  <a href="/attachments/registers/47381054.pdf">Environmental and Social Data Sheet</a>
  <a href="/en/press/2012-release.htm">Press release</a>
</main></body></html>
"""


def test_parse_extracts_title_and_pdf():
    rec = parse_project(SAMPLE, "20120430", "https://example/20120430")
    assert "DUDDON" in rec["title"]
    assert rec["n_pdfs"] == 1
    assert rec["documents"][0]["href"].endswith("47381054.pdf")


def test_pdf_regex():
    assert PDF_RE.search("foo/bar.pdf")
    assert not PDF_RE.search("foo/bar.htm")


def test_norm():
    assert _norm("  Düdd?on, S.A. ") == _norm("DÜDDON SA") or _norm("Duddon  SA ") == "DUDDON SA"
