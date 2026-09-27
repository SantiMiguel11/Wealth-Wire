"""URL canonicalization used for de-duplication."""
from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Pure tracking parameters. utm_* is matched by prefix.
TRACKING_PARAMS = {"fbclid", "gclid", "mc_cid", "mc_eid", "_hsenc", "_hsmi", "cmpid", "sr_share", "dclid", "msclkid"}


def canonicalize(url: str) -> str:
    """Lowercase scheme/host, drop default ports, fragments, tracking params and trailing slashes.

    >>> canonicalize("HTTPS://WWW.Example.com:443/a/b/?utm_source=x&id=2#frag")
    'https://www.example.com/a/b?id=2'
    """
    url = (url or "").strip()
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    port = parts.port
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        host = f"{host}:{port}"
    path = parts.path or ""
    while path.endswith("/") and len(path) > 0:
        path = path[:-1]
    query_pairs = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith("utm_") and k.lower() not in TRACKING_PARAMS
    ]
    query = urlencode(sorted(query_pairs))
    return urlunsplit((scheme, host, path, query, ""))


def clean_link(url: str) -> str:
    """For outgoing links: drop tracking params and the fragment, but otherwise keep the URL as published
    (path case, trailing slash) so it still resolves exactly as the outlet intended."""
    parts = urlsplit((url or "").strip())
    pairs = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if not k.lower().startswith("utm_") and k.lower() not in TRACKING_PARAMS]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(pairs), ""))
