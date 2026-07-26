import time
from collections import defaultdict
from fastapi import HTTPException, Request


_window_attempts: defaultdict[str, list[float]] = defaultdict(list)
_last_eviction: float = 0.0


def _trusted_proxies() -> list:
    """Parsed ``proxy_trusted_cidr`` networks, cached on the settings object."""
    import ipaddress
    from app.core.config import settings

    raw = getattr(settings, "proxy_trusted_cidr", "") or ""
    cached = getattr(_trusted_proxies, "_cache", None)
    if cached is not None and cached[0] == raw:
        return cached[1]
    nets = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            nets.append(ipaddress.ip_network(part, strict=False))
        except ValueError:
            continue
    _trusted_proxies._cache = (raw, nets)
    return nets


def _is_trusted_proxy(addr: str) -> bool:
    import ipaddress
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return False
    return any(ip in net for net in _trusted_proxies())


def _client_ip(request: Request) -> str:
    """Real client IP for rate-limiting purposes.

    ``X-Forwarded-For`` is attacker-controlled: anyone can send it. It is only
    consulted when the *immediate peer* is one of ``proxy_trusted_cidr``, and
    even then we walk the chain from the right, skipping trusted hops, because
    a client can prepend entries but cannot append them. Taking the left-most
    value (or trusting the header whenever the peer is loopback — the normal
    reverse-proxy case) let a caller mint a fresh bucket per request and walk
    straight through the login rate limit.
    """
    peer = request.client.host if request.client else ""
    if not peer:
        return "unknown"
    if not _is_trusted_proxy(peer):
        return peer

    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        for hop in reversed([h.strip() for h in xff.split(",") if h.strip()]):
            if not _is_trusted_proxy(hop):
                return hop
    return peer


def _evict_old_buckets(now: float, window_seconds: int) -> None:
    """Periodically prune empty buckets to prevent unbounded memory growth."""
    global _last_eviction
    if now - _last_eviction < 300:  # every 5 minutes
        return
    _last_eviction = now
    to_delete = [k for k, v in _window_attempts.items()
                 if not v or all(t <= now - window_seconds for t in v)]
    for k in to_delete:
        del _window_attempts[k]


# Per-account login lockout counters (complement to the per-IP rate limit)
_account_lockouts: dict[str, int] = {}
_locks_cleared_at: float = 0.0


def check_account_lockout(username: str, max_attempts: int, window_minutes: int) -> None:
    """Progressive per-account lockout with exponential backoff.

    Unlike the per-IP rate limit, this tracks lockout *counts* for repeated
    lockouts on the same account, increasing the window exponentially.
    """
    if not max_attempts or not window_minutes:
        return

    global _locks_cleared_at
    now = time.time()
    if now - _locks_cleared_at > 3600:
        _locks_cleared_at = now
        _account_lockouts.clear()

    count = _account_lockouts.get(username, 0) + 1
    _account_lockouts[username] = count

    if count <= 1:
        return

    # Exponential backoff: 2^count minutes
    backoff = min(2 ** count, 60) * 60  # cap at 1 hour
    if count > 3:
        raise HTTPException(
            status_code=429,
            detail=f"Too many lockouts on this account. Try again later.",
        )


def rate_limit(max_attempts: int = 5, window_seconds: int = 60):
    def limiter(request: Request):
        ip = _client_ip(request)
        key = f"{ip}:{request.url.path}"
        now = time.time()
        _evict_old_buckets(now, window_seconds)
        attempts = _window_attempts[key]
        attempts[:] = [t for t in attempts if t > now - window_seconds]
        if len(attempts) >= max_attempts:
            raise HTTPException(status_code=429, detail="Too many requests. Try again later.")
        attempts.append(now)
    return limiter
