"""Rate-limit tests."""

import pytest
from fastapi import HTTPException

from surgite import rate_limit


@pytest.fixture(autouse=True)
def _reset_buckets():
    rate_limit._reset_for_tests()
    yield
    rate_limit._reset_for_tests()


class _StubRequest:
    """Minimal request with forwarding and peer addresses."""

    def __init__(self, ip="1.2.3.4", fwd=None):
        self.headers = {"x-forwarded-for": fwd} if fwd else {}
        self.client = type("C", (), {"host": ip})()


def test_allows_up_to_limit():
    for _ in range(rate_limit._SUMMARY_IP_REQUESTS):
        rate_limit.check_ip_outer_rate_limit(_StubRequest())


def test_blocks_request_over_limit():
    for _ in range(rate_limit._SUMMARY_IP_REQUESTS):
        rate_limit.check_ip_outer_rate_limit(_StubRequest())
    with pytest.raises(HTTPException) as exc:
        rate_limit.check_ip_outer_rate_limit(_StubRequest())
    assert exc.value.status_code == 429
    assert "Retry-After" in exc.value.headers


def test_separate_buckets_per_ip():
    for _ in range(rate_limit._SUMMARY_IP_REQUESTS):
        rate_limit.check_ip_outer_rate_limit(_StubRequest(ip="1.1.1.1"))
    rate_limit.check_ip_outer_rate_limit(_StubRequest(ip="2.2.2.2"))


def test_honors_x_forwarded_for_when_trusted(monkeypatch):
    monkeypatch.setattr(rate_limit, "TRUSTED_PROXIES", ["10.0.0.0/8", "127.0.0.1"])
    for _ in range(rate_limit._SUMMARY_IP_REQUESTS):
        rate_limit.check_ip_outer_rate_limit(_StubRequest(fwd="9.9.9.9", ip="10.0.0.1"))
    rate_limit.check_ip_outer_rate_limit(_StubRequest(ip="10.0.0.1"))


def test_ignores_x_forwarded_for_when_untrusted():
    for _ in range(rate_limit._SUMMARY_IP_REQUESTS):
        rate_limit.check_ip_outer_rate_limit(_StubRequest(fwd="9.9.9.9", ip="1.2.3.4"))
    with pytest.raises(HTTPException) as exc:
        rate_limit.check_ip_outer_rate_limit(_StubRequest(fwd="8.8.8.8", ip="1.2.3.4"))
    assert exc.value.status_code == 429


def test_window_expiry_resets_bucket(monkeypatch):
    fake_now = [1000.0]
    monkeypatch.setattr(rate_limit.time, "monotonic", lambda: fake_now[0])
    for _ in range(rate_limit._SUMMARY_IP_REQUESTS):
        rate_limit.check_ip_outer_rate_limit(_StubRequest())
    fake_now[0] += rate_limit._SUMMARY_IP_WINDOW + 0.1
    rate_limit.check_ip_outer_rate_limit(_StubRequest())


# --- wired into the /summary handler ----------------------------------------


def test_summary_without_ai_is_not_rate_limited(client):
    for _ in range(rate_limit._SUMMARY_USER_REQUESTS + 5):
        assert client.get("/summary").status_code == 200


def test_summary_with_ai_returns_429_after_limit(client, monkeypatch):
    for _ in range(rate_limit._SUMMARY_USER_REQUESTS):
        r = client.get("/summary?ai=true&provider=groq")
        assert r.status_code == 400  # GROQ_API_KEY empty in conftest
    r = client.get("/summary?ai=true&provider=groq")
    assert r.status_code == 429
    assert r.headers.get("retry-after")
