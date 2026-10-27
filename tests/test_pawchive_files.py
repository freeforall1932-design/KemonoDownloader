"""Tests for the Pawchive/Kemono file-model resolver (no Qt, no network)."""

import hashlib
from datetime import datetime, timedelta, timezone

import pytest

from kemonodownloader import pawchive_files as pf

PAWCHIVE_CFG = {
    "domain": "pawchive.pw",
    "base_url": "https://pawchive.pw",
    "api_base": "https://pawchive.pw/api/v1",
    "file_base_url": "https://file.pawchive.pw",
    "referer": "https://pawchive.pw/",
}
KEMONO_CFG = {
    "domain": "kemono.cr",
    "base_url": "https://kemono.cr",
    "api_base": "https://kemono.cr/api/v1",
    "file_base_url": "https://kemono.cr",
    "referer": "https://kemono.cr/",
}

SHA = "a" * 64
PATH = f"/ab/cd/{SHA}.png"


class TestSha256FromPath:
    def test_extracts_from_relative_path(self):
        assert pf.sha256_from_path(PATH) == SHA

    def test_extracts_from_absolute_url_with_query(self):
        url = f"https://file.pawchive.pw/data/ab/cd/{SHA}.png?f=name.png"
        assert pf.sha256_from_path(url) == SHA

    def test_extracts_from_thumbnail_url(self):
        url = f"https://img.pawchive.pw/thumbnail/data/ab/cd/{SHA}.png"
        assert pf.sha256_from_path(url) == SHA

    @pytest.mark.parametrize(
        "value", [None, "", "/ab/cd/not-a-hash.png", "/ab/cd/short.png"]
    )
    def test_returns_none_for_non_hash_names(self, value):
        assert pf.sha256_from_path(value) is None


class TestSizeCap:
    def test_tiers(self):
        assert pf.size_cap_bytes(0) == 100 * 1024 * 1024
        assert pf.size_cap_bytes(249) == 100 * 1024 * 1024
        assert pf.size_cap_bytes(250) == 1024 * 1024 * 1024
        assert pf.size_cap_bytes(5000) == 5 * 1024 * 1024 * 1024

    @pytest.mark.parametrize("value", [None, "abc", -5])
    def test_unknown_gets_most_generous_cap(self, value):
        assert pf.size_cap_bytes(value) == 5 * 1024 * 1024 * 1024

    def test_human_size(self):
        assert pf.human_size(100 * 1024 * 1024) == "100 MB"
        assert pf.human_size(1024 * 1024 * 1024) == "1.0 GB"


class TestClassicModel:
    def test_builds_file_host_url(self):
        source = pf.resolve_file({"name": "a.png", "path": PATH}, PAWCHIVE_CFG)
        assert source.kind == pf.FULL
        assert source.reason == pf.REASON_CLASSIC
        assert source.available
        assert source.url == f"https://file.pawchive.pw/data/ab/cd/{SHA}.png"
        assert source.append_filename is True

    def test_node_field_is_advisory_only(self):
        source = pf.resolve_file(
            {"name": "a.png", "path": PATH, "node": 2}, PAWCHIVE_CFG
        )
        assert source.url == f"https://file.pawchive.pw/data/ab/cd/{SHA}.png"


class TestPreviewOnlyModel:
    def test_preview_only_falls_back_to_thumbnail(self):
        source = pf.resolve_file(
            {"name": "a.png", "path": PATH, "preview_only": True}, PAWCHIVE_CFG
        )
        assert source.kind == pf.THUMBNAIL
        assert source.reason == pf.REASON_PREVIEW_ONLY
        assert source.degraded
        assert source.url == f"https://img.pawchive.pw/thumbnail/data/ab/cd/{SHA}.png"

    def test_expired_temp_url_falls_back_to_thumbnail(self):
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        source = pf.resolve_file(
            {
                "name": "a.png",
                "path": PATH,
                "preview_only": True,
                "temp_url": "https://t1.pawchive.pw/f/x/a.png?e=1&s=2",
                "temp_expires": past,
            },
            PAWCHIVE_CFG,
        )
        assert source.kind == pf.THUMBNAIL
        assert "t1.pawchive.pw" not in (source.url or "")

    def test_expired_temp_url_on_classic_file_still_uses_classic_host(self):
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        source = pf.resolve_file(
            {
                "name": "a.png",
                "path": PATH,
                "temp_url": "https://t1.pawchive.pw/f/x/a.png",
                "temp_expires": past,
            },
            PAWCHIVE_CFG,
        )
        assert source.kind == pf.FULL
        assert source.url.startswith("https://file.pawchive.pw/data/")


class TestSignedModel:
    def test_usable_temp_url_wins(self):
        future = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
        temp = "https://t1.pawchive.pw/f/80033c7e/a.png?e=1793161434&s=deadbeef"
        source = pf.resolve_file(
            {
                "name": "a.png",
                "path": PATH,
                "preview_only": True,
                "temp_url": temp,
                "temp_expires": future,
            },
            PAWCHIVE_CFG,
        )
        assert source.kind == pf.TEMP
        assert source.signed is True
        assert source.url == temp
        # never append ?f= to a signed link
        assert source.append_filename is False

    def test_temp_url_without_expiry_is_usable(self):
        source = pf.resolve_file(
            {"name": "a.png", "temp_url": "https://t1.pawchive.pw/f/1/a.png"},
            PAWCHIVE_CFG,
        )
        assert source.kind == pf.TEMP

    def test_z_suffix_expiry_is_parsed(self):
        future = (datetime.now(timezone.utc) + timedelta(days=2)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        assert pf.temp_url_is_usable(
            {"temp_url": "https://t1.pawchive.pw/x", "temp_expires": future}
        )

    def test_expiry_without_timezone_treated_as_utc(self):
        future = (datetime.now(timezone.utc) + timedelta(days=2)).strftime(
            "%Y-%m-%dT%H:%M:%S"
        )
        assert pf.temp_url_is_usable(
            {"temp_url": "https://t1.pawchive.pw/x", "temp_expires": future}
        )


class TestUnavailableModel:
    def test_deferred_without_path(self):
        source = pf.resolve_file(
            {"name": "772606615.mp4", "deferred": True}, PAWCHIVE_CFG
        )
        assert source.kind == pf.UNAVAILABLE
        assert source.reason == pf.REASON_DEFERRED

    def test_named_without_path(self):
        source = pf.resolve_file({"name": "x.png"}, PAWCHIVE_CFG)
        assert source.kind == pf.UNAVAILABLE
        assert source.reason == pf.REASON_NOT_IMPORTED

    @pytest.mark.parametrize("value", [None, {}, "nope", 5])
    def test_garbage_input(self, value):
        source = pf.resolve_file(value, PAWCHIVE_CFG)
        assert source.kind == pf.UNAVAILABLE
        assert source.reason == pf.REASON_MISSING


class TestHasFull:
    def test_has_full_false_degrades_to_thumbnail(self):
        source = pf.resolve_file(
            {"name": "a.png", "path": PATH}, PAWCHIVE_CFG, post={"has_full": False}
        )
        assert source.kind == pf.THUMBNAIL
        assert source.reason == pf.REASON_HAS_FULL_FALSE

    def test_preview_only_beats_has_full_false(self):
        source = pf.resolve_file(
            {"name": "a.png", "path": PATH, "preview_only": True},
            PAWCHIVE_CFG,
            post={"has_full": False},
        )
        assert source.reason == pf.REASON_PREVIEW_ONLY

    def test_has_full_true_keeps_full_res(self):
        source = pf.resolve_file(
            {"name": "a.png", "path": PATH}, PAWCHIVE_CFG, post={"has_full": True}
        )
        assert source.kind == pf.FULL


class TestKemonoSite:
    def test_kemono_urls_keep_root_data_host(self):
        source = pf.resolve_file({"name": "a.png", "path": PATH}, KEMONO_CFG)
        assert source.url == f"https://kemono.cr/ab/cd/{SHA}.png"

    def test_thumbnail_builder_for_kemono(self):
        url = pf.resolve_thumbnail({"path": PATH}, KEMONO_CFG)
        assert url.startswith("https://img.kemono.cr/thumbnail/")


class TestPreviewState:
    @pytest.mark.parametrize("state", ["pending", "PENDING", "Pending"])
    def test_pending(self, state):
        assert pf.is_pending_post({"preview_state": state})

    @pytest.mark.parametrize("post", [{}, None, {"preview_state": "scraped"}, "x"])
    def test_not_pending(self, post):
        assert not pf.is_pending_post(post)

    def test_scraped(self):
        assert pf.is_scraped_post({"preview_state": "scraped"})
        assert not pf.is_scraped_post({"preview_state": "pending"})


class TestDigests:
    def test_compute_and_verify(self, tmp_path):
        payload = b"pawchive test payload"
        target = tmp_path / "file.bin"
        target.write_bytes(payload)
        md5_hex, sha_hex = pf.compute_digests(str(target))
        assert md5_hex == hashlib.md5(payload).hexdigest()
        assert sha_hex == hashlib.sha256(payload).hexdigest()
        assert pf.verify_content_sha256(str(target), sha_hex) is True
        assert pf.verify_content_sha256(str(target), "b" * 64) is False
        assert pf.verify_content_sha256(str(target), None) is None
        assert pf.verify_content_sha256(str(target), "nonsense") is None

    def test_expected_hash_from_url(self):
        url = f"https://file.pawchive.pw/data/ab/cd/{SHA}.png?f=x.png"
        assert pf.expected_sha256_for_url(url) == SHA
        # signed links do not carry the hash
        assert (
            pf.expected_sha256_for_url("https://t1.pawchive.pw/f/1/a.png?e=1") is None
        )
