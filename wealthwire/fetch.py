"""Polite HTTP fetching: descriptive User-Agent, per-host delay, timeouts, one retry with backoff,
conditional GET, and robots.txt checks for non-feed fetches."""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib import robotparser
from urllib.parse import urlsplit

import httpx
import yaml

RETRY_STATUSES = {429, 500, 502, 503, 504}


@dataclass
class FetchResult:
    url: str                 # final URL after redirects
    status: int              # HTTP status, 0 when the request never completed
    text: str = ""
    content: bytes = b""
    content_type: str = ""
    not_modified: bool = False
    error: str = ""          # exact failure reason for SOURCES.md

    @property
    def ok(self) -> bool:
        return self.status == 200 and not self.error

    def describe_failure(self) -> str:
        if self.error:
            return self.error
        return f"HTTP {self.status}"


class Fetcher:
    def __init__(
        self,
        user_agent: str,
        per_host_delay: float = 2.0,
        timeout: float = 15.0,
        retries: int = 1,
        backoff: float = 2.0,
        conn: sqlite3.Connection | None = None,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.per_host_delay = per_host_delay
        self.retries = retries
        self.backoff = backoff
        self.conn = conn
        self._sleep = sleep
        self._clock = clock
        self._last_request: dict[str, float] = {}
        self.request_log: list[tuple[str, str]] = []  # (host, url) in order — used by tests
        self.client = httpx.Client(
            headers={"User-Agent": user_agent, "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, text/html;q=0.8, */*;q=0.5"},
            timeout=timeout,
            follow_redirects=True,
            transport=transport,
        )
        self.robots = RobotsCache(self, user_agent)

    def close(self) -> None:
        self.client.close()

    # -- politeness -----------------------------------------------------------------------------
    def _wait_for_host(self, host: str) -> None:
        last = self._last_request.get(host)
        if last is not None:
            gap = self._clock() - last
            if gap < self.per_host_delay:
                self._sleep(self.per_host_delay - gap)
        self._last_request[host] = self._clock()

    # -- conditional GET cache ------------------------------------------------------------------
    def _cache_get(self, url: str) -> tuple[str | None, str | None]:
        if not self.conn:
            return None, None
        row = self.conn.execute("SELECT etag, last_modified FROM http_cache WHERE url=?", (url,)).fetchone()
        return (row["etag"], row["last_modified"]) if row else (None, None)

    def _cache_put(self, url: str, etag: str | None, last_modified: str | None) -> None:
        if not self.conn or not (etag or last_modified):
            return
        self.conn.execute(
            "INSERT INTO http_cache(url, etag, last_modified) VALUES (?,?,?) "
            "ON CONFLICT(url) DO UPDATE SET etag=excluded.etag, last_modified=excluded.last_modified",
            (url, etag, last_modified),
        )

    # -- main entry -----------------------------------------------------------------------------
    def get(self, url: str, conditional: bool = False) -> FetchResult:
        host = (urlsplit(url).hostname or "").lower()
        headers = {}
        if conditional:
            etag, last_modified = self._cache_get(url)
            if etag:
                headers["If-None-Match"] = etag
            if last_modified:
                headers["If-Modified-Since"] = last_modified
        attempt = 0
        while True:
            self._wait_for_host(host)
            self.request_log.append((host, url))
            try:
                resp = self.client.get(url, headers=headers)
            except httpx.ProxyError as exc:
                result = FetchResult(url, 0, error=f"network proxy refused connection ({exc})")
                retryable = False  # a policy denial will not change on retry
            except httpx.TimeoutException as exc:
                result = FetchResult(url, 0, error=f"timeout after {self.client.timeout.read}s ({type(exc).__name__})")
                retryable = True
            except httpx.HTTPError as exc:
                result = FetchResult(url, 0, error=f"{type(exc).__name__}: {exc}")
                retryable = True
            else:
                if resp.status_code == 304:
                    return FetchResult(str(resp.url), 304, not_modified=True)
                result = FetchResult(
                    str(resp.url),
                    resp.status_code,
                    text=resp.text if resp.status_code == 200 else "",
                    content=resp.content if resp.status_code == 200 else b"",
                    content_type=resp.headers.get("content-type", ""),
                )
                if resp.status_code == 200:
                    if conditional:
                        self._cache_put(url, resp.headers.get("etag"), resp.headers.get("last-modified"))
                    return result
                retryable = resp.status_code in RETRY_STATUSES
            if not retryable or attempt >= self.retries:
                return result
            attempt += 1
            self._sleep(self.backoff * attempt)


class RobotsCache:
    """robots.txt per host, parsed with urllib.robotparser. Fetched with the same polite client."""

    def __init__(self, fetcher: Fetcher, user_agent: str):
        self.fetcher = fetcher
        self.user_agent = user_agent
        self._parsers: dict[str, robotparser.RobotFileParser | None] = {}
        self._errors: dict[str, str] = {}

    def check(self, url: str) -> tuple[bool, str]:
        """Return (allowed, reason). reason explains a disallow."""
        parts = urlsplit(url)
        base = f"{parts.scheme}://{parts.netloc}"
        if base not in self._parsers:
            rp = robotparser.RobotFileParser()
            res = self.fetcher.get(base + "/robots.txt")
            if res.status == 200:
                rp.parse(res.text.splitlines())
            elif res.status in (401, 403):
                rp.disallow_all = True
                self._errors[base] = f"robots.txt returned HTTP {res.status} (treated as disallow-all)"
            elif res.status and 400 <= res.status < 500:
                rp.allow_all = True
            else:
                # Could not fetch robots.txt at all (network error / 5xx): be conservative.
                rp.disallow_all = True
                self._errors[base] = f"robots.txt unavailable ({res.describe_failure()}); not crawling"
            self._parsers[base] = rp
        rp = self._parsers[base]
        allowed = rp.can_fetch(self.user_agent, url)
        if allowed:
            return True, ""
        return False, self._errors.get(base) or f"robots.txt disallows {parts.path or '/'}"


class FixtureTransport(httpx.BaseTransport):
    """Serve saved files instead of the network. Used by tests and the offline demo.

    `routes.yaml` in the fixture dir maps URL → {file, status, headers}. Unmapped URLs → 404.
    """

    def __init__(self, fixture_dir: Path):
        self.dir = Path(fixture_dir)
        data = yaml.safe_load((self.dir / "routes.yaml").read_text(encoding="utf-8")) or {}
        self.routes: dict[str, dict] = data.get("routes", {})
        self.requests: list[httpx.Request] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        url = str(request.url)
        route = self.routes.get(url)
        if route is None:  # httpx normalizes "https://host" to "https://host/"
            alt = url[:-1] if url.endswith("/") else url + "/"
            route = self.routes.get(alt)
        if route is None:
            return httpx.Response(404, text="not found", request=request)
        headers = dict(route.get("headers") or {})
        etag = headers.get("ETag") or headers.get("etag")
        if etag and request.headers.get("if-none-match") == etag:
            return httpx.Response(304, headers=headers, request=request)
        status = int(route.get("status", 200))
        body = b""
        if route.get("file"):
            body = (self.dir / route["file"]).read_bytes()
        elif route.get("body") is not None:
            body = str(route["body"]).encode()
        headers.setdefault("content-type", route.get("content_type", "application/xml"))
        return httpx.Response(status, content=body, headers=headers, request=request)
