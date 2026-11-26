"""Pace NAV requests to each provider host."""

from collections.abc import Iterator
from contextlib import contextmanager
from http.client import HTTPResponse
from time import monotonic, sleep
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

REQUEST_PAUSE = 1.0
_last_request_end: dict[str, float] = {}


@contextmanager
def open_url(url: str | Request, *, timeout: float) -> Iterator[HTTPResponse]:
    host = urlsplit(url.full_url if isinstance(url, Request) else url).hostname
    if host is None:
        raise ValueError("Provider request URL must have a hostname")

    if (last_end := _last_request_end.get(host)) is not None:
        delay = last_end + REQUEST_PAUSE - monotonic()
        if delay > 0:
            sleep(delay)

    try:
        with urlopen(url, timeout=timeout) as response:
            yield response
    finally:
        _last_request_end[host] = monotonic()
