"""The auth cookie must come back on the next request.

``_cookie_domain`` returned the host from ``base_url`` for anything that was not
localhost, including bare IP addresses. RFC 6265's Domain attribute is defined
for domain names, and pinning it to one address breaks every other address the
same host answers on.

Found on a bare-metal deployment whose NIC carried two addresses: the installer
derived ``RT_BASE_URL=http://192.168.0.164`` from the kernel's preferred source
address, the operator browsed to ``192.168.0.163``, and the response carried
``Domain=192.168.0.164``. Login returned 200 and every request after it returned
401, because the cookie was set and then never sent back.
"""

from __future__ import annotations

import pytest

from app.core import auth
from app.core.config import settings


@pytest.fixture()
def base_url(monkeypatch):
    def _set(url: str):
        monkeypatch.setattr(settings, "base_url", url)
    return _set


# ── The defect ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("url", [
    "http://192.168.0.164",
    "http://192.168.0.164:8000",
    "https://10.0.0.5",
    "http://172.16.3.9:8000",
])
def test_ipv4_gets_a_host_only_cookie(base_url, url):
    base_url(url)
    assert auth._cookie_domain() is None, \
        "an IP literal in Domain pins the cookie to one address"


@pytest.mark.parametrize("url", ["http://[::1]:8000", "https://[2001:db8::1]"])
def test_ipv6_gets_a_host_only_cookie(base_url, url):
    base_url(url)
    assert auth._cookie_domain() is None


# ── What must keep working ───────────────────────────────────────────────────

@pytest.mark.parametrize("url,want", [
    ("https://reqs.example.com", "reqs.example.com"),
    ("http://reqs.example.com:8000", "reqs.example.com"),
    ("https://sub.domain.example.co.uk", "sub.domain.example.co.uk"),
])
def test_real_domains_still_set_the_attribute(base_url, url, want):
    base_url(url)
    assert auth._cookie_domain() == want


@pytest.mark.parametrize("url", [
    "http://localhost:8000", "http://127.0.0.1", "http://0.0.0.0:8000",
])
def test_loopback_stays_host_only(base_url, url):
    base_url(url)
    assert auth._cookie_domain() is None


@pytest.mark.parametrize("url", ["", "not-a-url", "localhost:8000"])
def test_malformed_base_url_is_not_fatal(base_url, url):
    base_url(url)
    assert auth._cookie_domain() is None


def test_a_host_only_cookie_is_returned_to_any_address(base_url):
    """The property that actually matters, end to end.

    A cookie with no Domain is returned for whatever host was used, which is why
    a deployment reachable on several addresses works at all.
    """
    from fastapi import Response
    base_url("http://192.168.0.164")
    resp = Response()
    auth.set_auth_cookies(resp, "admin", auth.create_token("admin", "admin"))
    raw = "\n".join(v.decode() for k, v in resp.raw_headers if k == b"set-cookie")
    assert raw, "no cookies were set"
    assert "Domain=" not in raw, f"cookie pinned to a domain: {raw}"
