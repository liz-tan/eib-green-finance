"""Polite, cached HTTP helpers shared across the pipeline.

Every fetch is cached on disk by URL, so a re-run never re-downloads a page you
already have, and the portal is hit at most once per resource. Requests are
rate-limited and retried with exponential backoff.
"""
from __future__ import annotations
import hashlib
import time
from pathlib import Path

import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

_LAST_CALL = {"t": 0.0}


def _throttle(min_delay: float) -> None:
    dt = time.time() - _LAST_CALL["t"]
    if dt < min_delay:
        time.sleep(min_delay - dt)
    _LAST_CALL["t"] = time.time()


def _cache_path(cache_dir: Path, url: str, suffix: str) -> Path:
    key = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{key}{suffix}"


class Fetcher:
    """A cached, rate-limited session. One instance per pilot run."""

    def __init__(self, cache_dir: str, contact: str = "research-scraper",
                 min_delay: float = 1.5, max_retries: int = 4):
        self.cache_dir = Path(cache_dir)
        self.min_delay = min_delay
        self.max_retries = max_retries
        self.session = requests.Session()
        # Generic, honest User-Agent. Add your own contact if you like — do not
        # hard-code anyone's private email here.
        self.session.headers.update({
            "User-Agent": f"{contact} (polite academic scraper; caches, rate-limited)"
        })

    def _get(self, url: str) -> requests.Response:
        @retry(stop=stop_after_attempt(self.max_retries),
               wait=wait_exponential(multiplier=2, min=2, max=60),
               retry=retry_if_exception_type((requests.RequestException,)),
               reraise=True)
        def _inner() -> requests.Response:
            _throttle(self.min_delay)
            r = self.session.get(url, timeout=45)
            r.raise_for_status()
            return r
        return _inner()

    def get_text(self, url: str) -> str:
        """Fetch an HTML page as text, cached."""
        cp = _cache_path(self.cache_dir, url, ".html")
        if cp.exists():
            return cp.read_text(encoding="utf-8", errors="replace")
        html = self._get(url).text
        cp.write_text(html, encoding="utf-8", errors="replace")
        return html

    def get_pdf(self, url: str) -> Path:
        """Download a PDF, cached; returns the local path."""
        cp = _cache_path(self.cache_dir, url, ".pdf")
        if not cp.exists():
            cp.write_bytes(self._get(url).content)
        return cp

    def get_json(self, url: str):
        """Fetch a JSON endpoint, cached."""
        import json
        cp = _cache_path(self.cache_dir, url, ".json")
        if cp.exists():
            return json.loads(cp.read_text(encoding="utf-8"))
        data = self._get(url).json()
        cp.write_text(json.dumps(data), encoding="utf-8")
        return data
