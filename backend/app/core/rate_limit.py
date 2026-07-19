import time
from collections import defaultdict
from fastapi import HTTPException, Request


_window_attempts: defaultdict[str, list[float]] = defaultdict(list)


def rate_limit(max_attempts: int = 5, window_seconds: int = 60):
    def limiter(request: Request):
        ip = request.client.host if request.client else "unknown"
        now = time.time()
        attempts = _window_attempts[ip]
        attempts[:] = [t for t in attempts if t > now - window_seconds]
        if len(attempts) >= max_attempts:
            raise HTTPException(status_code=429, detail="Too many requests. Try again later.")
        attempts.append(now)
    return limiter
