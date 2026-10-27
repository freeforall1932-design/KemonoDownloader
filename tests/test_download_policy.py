"""Tests for the Pawchive download policy (no Qt, no network)."""

import threading
import time

import pytest

from kemonodownloader import download_policy as policy


@pytest.fixture(autouse=True)
def _reset_limiter():
    policy.reset_pawchive_limiter()
    yield
    policy.reset_pawchive_limiter()


class TestUserAgent:
    def test_is_identifiable_and_versioned(self):
        assert policy.IDENTIFIABLE_USER_AGENT.startswith("KemonoDownloader/")
        assert "mailto:" in policy.IDENTIFIABLE_USER_AGENT
        from kemonodownloader import __version__

        assert __version__ in policy.IDENTIFIABLE_USER_AGENT

    def test_no_browser_impersonation(self):
        assert "Mozilla" not in policy.IDENTIFIABLE_USER_AGENT


class TestIsPawchiveUrl:
    @pytest.mark.parametrize(
        "url",
        [
            "https://pawchive.pw/api/v1/posts",
            "https://file.pawchive.pw/data/ab/cd/x.png",
            "https://img.pawchive.pw/thumbnail/data/ab/cd/x.png",
            "https://t1.pawchive.pw/f/1/x.png",
        ],
    )
    def test_pawchive_hosts(self, url):
        assert policy.is_pawchive_url(url)

    @pytest.mark.parametrize(
        "url",
        [
            "https://kemono.cr/api/v1/posts",
            "https://file.kemono.cr/data/ab/cd/x.png",
            "https://pawchive.pw.example.com/x",
            "not a url",
            "",
        ],
    )
    def test_other_hosts(self, url):
        assert not policy.is_pawchive_url(url)

    @pytest.mark.parametrize(
        "host",
        ["pawchive.pw", "file.pawchive.pw", "n1.pawchive.pw", "file.pawchive.co.uk"],
    )
    def test_forward_compatible_shapes(self, host, monkeypatch):
        monkeypatch.setattr(policy, "get_domains", lambda: ["kemono.cr"])
        assert policy.is_pawchive_hostname(host)

    @pytest.mark.parametrize(
        "host",
        ["pawchive.pw.example.com", "pawchive", "my-pawchive.pw"],
    )
    def test_lookalikes_rejected(self, host, monkeypatch):
        # Even with the remote domain list gone (so the built-in fallback is
        # the only known domain) a lookalike must not be throttled as Pawchive.
        monkeypatch.setattr(policy, "get_domains", lambda: ["kemono.cr"])
        assert not policy.is_pawchive_hostname(host)

    def test_unknown_suffix_may_overmatch_on_purpose(self, monkeypatch):
        """A rotated suffix is indistinguishable from a lookalike.

        Erring toward throttling an unrelated host is harmless; erring the
        other way would hammer Pawchive's next domain with unpaced requests.
        """
        monkeypatch.setattr(policy, "get_domains", lambda: ["kemono.cr"])
        assert policy.is_pawchive_hostname("pawchive.evil.pw")

    def test_deep_subdomain_of_real_domain_matches(self):
        # File hosts are subdomains; depth alone must not disqualify them.
        assert policy.is_pawchive_hostname("a.b.pawchive.pw")

    def test_rotated_suffix_is_still_matched(self, monkeypatch):
        """The domain list is authoritative: .st must keep working after .pw ships."""
        monkeypatch.setattr(
            policy, "get_domains", lambda: ["kemono.cr", "coomer.st", "pawchive.st"]
        )
        assert policy.is_pawchive_url("https://file.pawchive.st/data/aa/bb/c.png")
        assert policy.is_pawchive_url("https://pawchive.st/api/v1/posts")
        assert not policy.is_pawchive_url("https://kemono.cr/api/v1/posts")

    def test_unknown_future_suffix_still_paced(self, monkeypatch):
        monkeypatch.setattr(policy, "get_domains", lambda: ["kemono.cr", "pawchive.pw"])
        assert policy.is_pawchive_url("https://file.pawchive.xyz/data/aa/bb/c.png")


class TestRequestHeaders:
    def test_pawchive_gets_identifiable_ua(self):
        headers = policy.get_request_headers(
            {"Referer": "x"}, "https://file.pawchive.pw/a"
        )
        assert headers["User-Agent"] == policy.IDENTIFIABLE_USER_AGENT
        assert headers["Referer"] == "x"

    def test_other_hosts_untouched(self):
        headers = policy.get_request_headers(
            {"User-Agent": "custom"}, "https://kemono.cr/a"
        )
        assert headers["User-Agent"] == "custom"

    def test_does_not_mutate_caller_dict(self):
        original = {"User-Agent": "browser"}
        policy.get_request_headers(original, "https://pawchive.pw/api")
        assert original == {"User-Agent": "browser"}


class TestRetryAfter:
    @pytest.mark.parametrize("value,expected", [("30", 30.0), ("0", 0.0), (" 7 ", 7.0)])
    def test_seconds(self, value, expected):
        assert policy.retry_after_seconds({"Retry-After": value}) == expected

    def test_case_insensitive_key(self):
        assert policy.retry_after_seconds({"retry-after": "5"}) == 5.0

    def test_missing_or_garbage(self):
        assert policy.retry_after_seconds({}) is None
        assert policy.retry_after_seconds(None) is None
        assert policy.retry_after_seconds({"Retry-After": "soon"}) is None

    def test_capped(self):
        assert (
            policy.retry_after_seconds({"Retry-After": "999999"})
            == policy.MAX_RETRY_AFTER_SECONDS
        )

    def test_http_date(self):
        import email.utils

        future = email.utils.formatdate(time.time() + 42, usegmt=True)
        seconds = policy.retry_after_seconds({"Retry-After": future})
        assert seconds is not None and 35 <= seconds <= 45

    def test_http_date_in_the_past_is_zero(self):
        import email.utils

        past = email.utils.formatdate(time.time() - 100, usegmt=True)
        assert policy.retry_after_seconds({"Retry-After": past}) == 0.0


class _FakeClock:
    """Deterministic clock so limiter tests never touch wall time."""

    def __init__(self) -> None:
        self.now = 1000.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += max(seconds, 0.0)


@pytest.fixture
def clock(monkeypatch):
    """Give the policy module its own clock so nothing else is affected."""
    fake = _FakeClock()
    monkeypatch.setattr(policy, "time", fake)
    return fake


class TestDownloadLimiter:
    def test_first_slot_is_immediate(self, clock):
        assert policy.acquire_pawchive_download(
            "https://file.pawchive.pw/data/a", lambda: True
        )
        assert policy._pawchive_limiter.active == 1
        policy.release_pawchive_download("https://file.pawchive.pw/data/a")
        assert policy._pawchive_limiter.active == 0

    def test_second_slot_waits_for_interval(self, clock):
        url = "https://file.pawchive.pw/data/a"
        assert policy.acquire_pawchive_download(url, lambda: True)
        start = clock.now
        assert policy.acquire_pawchive_download(url, lambda: True)
        assert clock.now - start >= policy.PAWCHIVE_REQUEST_INTERVAL
        assert policy._pawchive_limiter.active == 2

    def test_active_cap_is_enforced(self, clock):
        url = "https://file.pawchive.pw/data/a"
        for _ in range(policy.PAWCHIVE_MAX_ACTIVE_DOWNLOADS):
            assert policy.acquire_pawchive_download(url, lambda: True)
        assert policy._pawchive_limiter.active == policy.PAWCHIVE_MAX_ACTIVE_DOWNLOADS

        # The next slot is refused once the worker is asked to stop.
        calls = {"n": 0}

        def is_running():
            calls["n"] += 1
            return calls["n"] < 20

        assert policy.acquire_pawchive_download(url, is_running) is False
        assert policy._pawchive_limiter.active == policy.PAWCHIVE_MAX_ACTIVE_DOWNLOADS

    def test_cancelled_acquire_returns_false(self, clock):
        for _ in range(policy.PAWCHIVE_MAX_ACTIVE_DOWNLOADS):
            policy.acquire_pawchive_download(
                "https://file.pawchive.pw/data/a", lambda: True
            )
        assert (
            policy.acquire_pawchive_download(
                "https://file.pawchive.pw/data/b", lambda: False
            )
            is False
        )

    def test_non_pawchive_acquire_is_free(self, clock):
        assert (
            policy.acquire_pawchive_download("https://kemono.cr/x", lambda: True)
            is True
        )
        assert policy._pawchive_limiter.active == 0
        # release must not drive the counter negative
        policy.release_pawchive_download("https://kemono.cr/x")
        assert policy._pawchive_limiter.active == 0

    def test_release_never_negative(self, clock):
        policy.release_pawchive_download("https://file.pawchive.pw/data/a")
        policy.release_pawchive_download("https://file.pawchive.pw/data/a")
        assert policy._pawchive_limiter.active == 0

    def test_defer_blocks_downloads(self, clock):
        url = "https://file.pawchive.pw/data/a"
        policy.defer_pawchive_requests(30)
        start = clock.now
        assert policy.acquire_pawchive_download(url, lambda: True)
        assert clock.now - start >= 30

    def test_reset_clears_state(self, clock):
        policy.acquire_pawchive_download(
            "https://file.pawchive.pw/data/a", lambda: True
        )
        policy.reset_pawchive_limiter()
        assert policy._pawchive_limiter.active == 0


class TestPacing:
    def test_second_request_waits(self, clock):
        assert policy.pace_pawchive_request("https://pawchive.pw/api/v1/posts")
        first = clock.now
        assert policy.pace_pawchive_request("https://pawchive.pw/api/v1/posts")
        assert clock.now - first >= policy.PAWCHIVE_REQUEST_INTERVAL

    def test_non_pawchive_is_not_paced(self, monkeypatch):
        calls = []
        monkeypatch.setattr(policy.time, "sleep", calls.append)
        assert policy.pace_pawchive_request("https://kemono.cr/api/v1/posts")
        assert calls == []

    def test_cancelled_pacing_returns_false(self):
        assert (
            policy.pace_pawchive_request(
                "https://pawchive.pw/api/v1/posts", lambda: False
            )
            is False
        )

    def test_defer_pushes_next_slot(self, clock):
        assert policy.pace_pawchive_request("https://pawchive.pw/a")
        policy.defer_pawchive_requests(30)
        start = clock.now
        assert policy.pace_pawchive_request("https://pawchive.pw/a")
        assert clock.now - start >= 30
