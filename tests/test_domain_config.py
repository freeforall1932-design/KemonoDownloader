"""Tests for domain configuration helpers, including the thumbnail URL builder."""

from kemonodownloader.domain_config import get_domain_config, to_thumbnail_url


def _pawchive_config():
    return get_domain_config("https://pawchive.pw/fanbox/user/1")


class TestToThumbnailUrl:
    def test_pawchive_data_path_becomes_thumbnail(self):
        cfg = _pawchive_config()
        out = to_thumbnail_url("/3f/21/abc.jpeg", cfg)
        assert out == "https://img.pawchive.pw/thumbnail/data/3f/21/abc.jpeg"

    def test_pawchive_full_url_is_rewritten(self):
        cfg = _pawchive_config()
        out = to_thumbnail_url("https://file.pawchive.pw/data/ab/cd/x.png", cfg)
        assert out == "https://img.pawchive.pw/thumbnail/data/ab/cd/x.png"

    def test_existing_thumbnail_url_passes_through(self):
        cfg = _pawchive_config()
        thumb = "https://img.pawchive.pw/thumbnail/data/ab/cd/x.png"
        assert to_thumbnail_url(thumb, cfg) == thumb

    def test_arbitrary_path_gets_data_prefix(self):
        cfg = _pawchive_config()
        out = to_thumbnail_url("some/weird/path.jpg", cfg)
        assert out == "https://img.pawchive.pw/thumbnail/data/some/weird/path.jpg"

    def test_empty_input(self):
        cfg = _pawchive_config()
        assert to_thumbnail_url("", cfg) == ""
        assert to_thumbnail_url(None, cfg) == ""

    def test_thumbnail_path_kept_verbatim(self):
        cfg = _pawchive_config()
        out = to_thumbnail_url("/thumbnail/data/aa/bb/c.jpeg", cfg)
        assert out == "https://img.pawchive.pw/thumbnail/data/aa/bb/c.jpeg"


class TestGetDomainConfig:
    def test_pawchive_special_case(self):
        cfg = _pawchive_config()
        assert cfg["domain"] == "pawchive.pw"
        assert cfg["api_base"] == "https://pawchive.pw/api/v1"
        assert cfg["file_base_url"] == "https://file.pawchive.pw"
