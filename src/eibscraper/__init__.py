"""EIB green-finance data pipeline (treatment side).

Modules run in pipeline order:
    harvest_ids  -> fetch_pages -> fetch_pdfs -> join_spine -> classify -> geocode
"""
__version__ = "0.1.0"
