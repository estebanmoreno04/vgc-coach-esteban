"""A polite HTTP client: robots.txt, rate limiting, disk cache and retries.

Every network request made by the resolver and the pipeline goes through
:class:`PoliteClient`. Tests replace it with an object exposing the same
``get_text`` method, so they never touch the network.
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request
import urllib.robotparser
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Protocol
from urllib.parse import urlsplit


class SourceError(RuntimeError):
    """A source could not be read (network, HTTP status, parsing)."""


class SourceBlocked(SourceError):
    """robots.txt disallows the request; the source must not be read."""


class TextClient(Protocol):
    def get_text(self, url: str, *, ttl_hours: float = 0) -> str: ...


ROBOTS_TTL = timedelta(hours=24)
MAX_RETRY_AFTER_SECONDS = 60.0
MAX_RESPONSE_BYTES = 16 * 1024 * 1024


@dataclass
class _Robots:
    parser: urllib.robotparser.RobotFileParser
    fetched_at: datetime


@dataclass
class PoliteClient:
    user_agent: str
    cache_dir: Path | None = None
    timeout_seconds: float = 30.0
    min_interval_seconds: float = 2.0
    max_retries: int = 2
    host_intervals: dict[str, float] = field(default_factory=dict)
    sleep: Callable[[float], None] = time.sleep
    clock: Callable[[], float] = time.monotonic
    _last_request: dict[str, float] = field(default_factory=dict)
    _robots: dict[str, _Robots] = field(default_factory=dict)

    @classmethod
    def from_config(cls, config: dict, *, root: Path) -> "PoliteClient":
        http = config["http"]
        return cls(
            user_agent=http["user_agent"],
            cache_dir=root / http["cache_dir"] if http.get("cache_dir") else None,
            timeout_seconds=float(http.get("timeout_seconds", 30)),
            min_interval_seconds=float(http.get("min_interval_seconds", 2)),
            max_retries=int(http.get("max_retries", 2)),
            host_intervals={
                str(host): float(seconds)
                for host, seconds in (http.get("host_min_interval_seconds") or {}).items()
            },
        )

    # -- public -----------------------------------------------------------

    def get_text(self, url: str, *, ttl_hours: float = 0) -> str:
        cached = self._read_cache(url, ttl_hours)
        if cached is not None:
            return cached
        if not self._allowed(url):
            raise SourceBlocked(f"robots.txt disallows {url}")
        body = self._fetch(url)
        self._write_cache(url, body)
        return body

    def get_bytes(self, url: str) -> bytes:
        """Binary download (images); callers keep their own cache."""
        if not self._allowed(url):
            raise SourceBlocked(f"robots.txt disallows {url}")
        return self._request(url)[0]

    # -- robots.txt -------------------------------------------------------

    def _allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        entry = self._robots.get(origin)
        now = datetime.now(timezone.utc)
        if entry is None or now - entry.fetched_at > ROBOTS_TTL:
            entry = _Robots(self._load_robots(origin), now)
            self._robots[origin] = entry
        return entry.parser.can_fetch(self.user_agent, url)

    def _load_robots(self, origin: str) -> urllib.robotparser.RobotFileParser:
        # RFC 9309: a missing robots.txt (4xx) allows everything; an
        # unreachable one (5xx, network error) must be treated as disallow-all.
        parser = urllib.robotparser.RobotFileParser(f"{origin}/robots.txt")
        try:
            body = self._fetch(f"{origin}/robots.txt", retries=0)
        except HTTPStatusError as exc:
            if 400 <= exc.status < 500:
                parser.allow_all = True
            else:
                parser.disallow_all = True
            return parser
        except SourceError:
            parser.disallow_all = True
            return parser
        parser.parse(body.splitlines())
        return parser

    # -- transport --------------------------------------------------------

    def _fetch(self, url: str, *, retries: int | None = None) -> str:
        raw, charset = self._request(url, retries=retries)
        return raw.decode(charset, errors="replace")

    def _request(self, url: str, *, retries: int | None = None) -> tuple[bytes, str]:
        attempts = (self.max_retries if retries is None else retries) + 1
        last_error: Exception | None = None
        for attempt in range(attempts):
            self._throttle(url)
            request = urllib.request.Request(
                url,
                headers={"User-Agent": self.user_agent, "Accept": "*/*"},
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                    raw = response.read(MAX_RESPONSE_BYTES + 1)
                    if len(raw) > MAX_RESPONSE_BYTES:
                        raise SourceError(f"{url}: response exceeded {MAX_RESPONSE_BYTES} bytes")
                    return raw, response.headers.get_content_charset() or "utf-8"
            except urllib.error.HTTPError as exc:
                last_error = HTTPStatusError(url, exc.code)
                if exc.code == 429 or exc.code >= 500:
                    if attempt + 1 < attempts:
                        self.sleep(_retry_after(exc, attempt))
                        continue
                raise last_error from exc
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_error = SourceError(f"{url}: {exc}")
                if attempt + 1 < attempts:
                    self.sleep(2.0 * (attempt + 1))
                    continue
        assert last_error is not None
        raise last_error

    def _throttle(self, url: str) -> None:
        host = urlsplit(url).netloc
        previous = self._last_request.get(host)
        if previous is not None:
            interval = self.host_intervals.get(host, self.min_interval_seconds)
            wait = interval - (self.clock() - previous)
            if wait > 0:
                self.sleep(wait)
        self._last_request[host] = self.clock()

    # -- cache ------------------------------------------------------------

    def _cache_path(self, url: str) -> Path | None:
        if self.cache_dir is None:
            return None
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{digest}.json"

    def _read_cache(self, url: str, ttl_hours: float) -> str | None:
        path = self._cache_path(url)
        if path is None or ttl_hours <= 0 or not path.exists():
            return None
        try:
            entry = json.loads(path.read_text(encoding="utf-8"))
            fetched_at = datetime.fromisoformat(entry["fetched_at"])
        except (OSError, ValueError, KeyError):
            return None
        if datetime.now(timezone.utc) - fetched_at > timedelta(hours=ttl_hours):
            return None
        return entry["body"]

    def _write_cache(self, url: str, body: str) -> None:
        path = self._cache_path(url)
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "url": url,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "body": body,
        }
        path.write_text(json.dumps(entry), encoding="utf-8")


class HTTPStatusError(SourceError):
    def __init__(self, url: str, status: int) -> None:
        super().__init__(f"{url}: HTTP {status}")
        self.status = status


def _retry_after(exc: urllib.error.HTTPError, attempt: int) -> float:
    header = exc.headers.get("Retry-After") if exc.headers else None
    try:
        return min(float(header), MAX_RETRY_AFTER_SECONDS)
    except (TypeError, ValueError):
        return min(5.0 * (attempt + 1), MAX_RETRY_AFTER_SECONDS)
