"""Process-local per-user and per-IP rate limits."""

import ipaddress
import os
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from surgite.config import TRUSTED_PROXIES

_SUMMARY_USER_REQUESTS = int(os.environ.get("SUMMARY_RATE_LIMIT_REQUESTS", "5"))
_SUMMARY_USER_WINDOW = int(os.environ.get("SUMMARY_RATE_LIMIT_WINDOW_SECONDS", "60"))
_SUMMARY_IP_REQUESTS = int(os.environ.get("IP_OUTER_RATE_LIMIT_REQUESTS", "100"))
_SUMMARY_IP_WINDOW = int(os.environ.get("IP_OUTER_RATE_LIMIT_WINDOW_SECONDS", "60"))

_ip_buckets: dict[str, deque[float]] = defaultdict(deque)
_user_buckets: dict[tuple[str, str], deque[float]] = defaultdict(deque)
_lock = threading.Lock()


def _client_ip(request: Request) -> str:
    """Use the forwarded IP only when the direct peer is trusted."""
    direct_peer = request.client.host if request.client else "unknown"
    fwd = request.headers.get("x-forwarded-for")
    if fwd and TRUSTED_PROXIES and _is_trusted(direct_peer):
        return fwd.split(",", 1)[0].strip()
    return direct_peer


def _is_trusted(ip: str) -> bool:
    """Match an IP against exact addresses and CIDRs."""
    for entry in TRUSTED_PROXIES:
        if "/" not in entry:
            if ip == entry:
                return True
            continue
        try:
            if ipaddress.ip_address(ip) in ipaddress.ip_network(entry, strict=False):
                return True
        except ValueError:
            continue
    return False


def _check_bucket(bucket: deque, limit: int, window: int, label: str) -> None:
    """Consume a bucket slot or raise 429 with Retry-After."""
    now = time.monotonic()
    cutoff = now - window
    while bucket and bucket[0] < cutoff:
        bucket.popleft()
    if len(bucket) >= limit:
        retry_after = max(1, int(window - (now - bucket[0])))
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded: max {limit} / {window}s per {label}",
            headers={"Retry-After": str(retry_after)},
        )
    bucket.append(now)


def _drop_empty_ip_bucket(ip: str) -> None:
    """Drop an empty IP bucket while the caller holds the lock."""
    bucket = _ip_buckets.get(ip)
    if bucket is not None and not bucket:
        del _ip_buckets[ip]


def check_user_rate_limit(
    request: Request, *, user_id: str, limit: int, window: int, name: str
) -> None:
    """Apply a named per-user limit."""
    with _lock:
        _check_bucket(_user_buckets[(user_id, name)], limit, window, f"user:{name}")


def check_ip_outer_rate_limit(request: Request) -> None:
    """Apply the outer per-IP limit."""
    ip = _client_ip(request)
    with _lock:
        _check_bucket(_ip_buckets[ip], _SUMMARY_IP_REQUESTS, _SUMMARY_IP_WINDOW, "IP")
        _drop_empty_ip_bucket(ip)


def check_summary_user_limit(request: Request, *, user_id: str) -> None:
    check_user_rate_limit(
        request,
        user_id=user_id,
        limit=_SUMMARY_USER_REQUESTS,
        window=_SUMMARY_USER_WINDOW,
        name="summary",
    )


def _reset_for_tests() -> None:
    """Clear all buckets between tests."""
    with _lock:
        _ip_buckets.clear()
        _user_buckets.clear()
