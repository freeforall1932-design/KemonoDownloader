"""Tests for the Pawchive / Kemono-family favorites helpers (no Qt required)."""

import json

from kemonodownloader import pawchive


class TestAuthCookieHeader:
    def test_plain_key_gets_session_cookie(self):
        assert pawchive.auth_cookie_header("abc123") == {"Cookie": "session=abc123"}

    def test_full_cookie_passes_through(self):
        assert pawchive.auth_cookie_header("connect.sid=s%3Axyz") == {
            "Cookie": "connect.sid=s%3Axyz"
        }

    def test_empty_credential(self):
        assert pawchive.auth_cookie_header("") == {"Cookie": "session="}


class TestExtractArtist:
    def test_standard_entry(self):
        entry = {"id": "77", "service": "fanbox", "name": "Alice"}
        assert pawchive.extract_artist(entry) == ("fanbox", "77", "Alice")

    def test_service_uppercased_and_stripped(self):
        entry = {"id": "9", "service": " PATREON "}
        assert pawchive.extract_artist(entry) == ("patreon", "9", "")

    def test_id_alias_user(self):
        entry = {"user": "123", "service": "pixiv"}
        assert pawchive.extract_artist(entry) == ("pixiv", "123", "")

    def test_id_alias_creator_id(self):
        entry = {"creator_id": "5", "service": "fantia"}
        assert pawchive.extract_artist(entry) == ("fantia", "5", "")

    def test_missing_service_returns_none(self):
        assert pawchive.extract_artist({"id": "1"}) is None

    def test_missing_id_returns_none(self):
        assert pawchive.extract_artist({"service": "fanbox"}) is None

    def test_non_dict_returns_none(self):
        assert pawchive.extract_artist("nope") is None
        assert pawchive.extract_artist(None) is None

    def test_name_falls_back_to_title(self):
        entry = {"id": "1", "service": "fanbox", "title": "The Title"}
        assert pawchive.extract_artist(entry) == ("fanbox", "1", "The Title")


class TestParseArtistEntries:
    def test_flat_list(self):
        payload = [
            {"id": "1", "service": "fanbox", "name": "A"},
            {"id": "2", "service": "patreon", "name": "B"},
        ]
        assert pawchive.parse_artist_entries(payload) == [
            ("fanbox", "1", "A"),
            ("patreon", "2", "B"),
        ]

    def test_artists_wrapper(self):
        payload = {"artists": [{"id": "1", "service": "fanbox"}]}
        assert pawchive.parse_artist_entries(payload) == [("fanbox", "1", "")]

    def test_creators_wrapper(self):
        payload = {"creators": [{"id": "9", "service": "fantia"}]}
        assert pawchive.parse_artist_entries(payload) == [("fantia", "9", "")]

    def test_data_wrapper(self):
        payload = {"data": [{"id": "3", "service": "pixiv"}]}
        assert pawchive.parse_artist_entries(payload) == [("pixiv", "3", "")]

    def test_empty_object(self):
        assert pawchive.parse_artist_entries({}) == []

    def test_invalid_entries_filtered(self):
        payload = [
            {"id": "1", "service": "fanbox"},
            {"service": "patreon"},  # missing id
            {"id": "2"},  # missing service
            "garbage",
        ]
        assert pawchive.parse_artist_entries(payload) == [("fanbox", "1", "")]

    def test_duplicates_deduped(self):
        payload = [
            {"id": "1", "service": "fanbox"},
            {"id": "1", "service": "fanbox"},
        ]
        assert pawchive.parse_artist_entries(payload) == [("fanbox", "1", "")]


class TestParseFavoritesJsonText:
    def test_standard_export(self):
        text = json.dumps(
            [{"id": "77", "service": "fanbox", "name": "X"}]
        )
        assert pawchive.parse_favorites_json_text(text) == [("fanbox", "77", "X")]

    def test_wrapped_export(self):
        text = json.dumps({"artists": [{"id": "1", "service": "pixiv"}]})
        assert pawchive.parse_favorites_json_text(text) == [("pixiv", "1", "")]

    def test_invalid_json_raises(self):
        import pytest

        with pytest.raises(ValueError):
            pawchive.parse_favorites_json_text("{not json")


class TestBuildCreatorUrl:
    def test_default_domain(self):
        url = pawchive.build_creator_url("fanbox", "77")
        assert url.startswith("https://pawchive.")
        assert url.endswith("/fanbox/user/77")

    def test_explicit_domain(self):
        url = pawchive.build_creator_url("patreon", "5", domain="kemono.su")
        assert url == "https://kemono.su/patreon/user/5"


class TestGetPawchiveDomain:
    def test_returns_pawchive_domain(self):
        domain = pawchive.get_pawchive_domain()
        assert domain.startswith("pawchive.")


class TestFetchFavoritesMocked:
    def test_fetch_favorites_parses_list(self, monkeypatch):
        class FakeResponse:
            status_code = 200
            content = b'[{"id": "77", "service": "fanbox", "name": "A"}]'

            def raise_for_status(self):
                return None

            def json(self):
                return [{"id": "77", "service": "fanbox", "name": "A"}]

        class FakeSession:
            def get(self, url, headers=None, timeout=None):
                assert "/api/v1/account/favorites" in url
                assert headers and "Cookie" in headers
                return FakeResponse()

        entries = pawchive.fetch_favorites(
            domain="pawchive.pw", api_key="abc", session=FakeSession()
        )
        assert entries == [("fanbox", "77", "A")]

    def test_fetch_recent_posts_creators_dedupes(self, monkeypatch):
        posts = [
            {"service": "fanbox", "user": "1", "title": "First"},
            {"service": "fanbox", "user": "1", "title": "Second"},
            {"service": "patreon", "user": "2", "title": "Other"},
        ]

        class FakeResponse:
            status_code = 200
            content = b"[]"

            def raise_for_status(self):
                return None

            def json(self):
                return posts

        class FakeSession:
            def get(self, url, headers=None, timeout=None):
                assert "/api/v1/posts?o=0" in url
                return FakeResponse()

        entries = pawchive.fetch_recent_posts_creators(
            domain="pawchive.pw", session=FakeSession()
        )
        assert entries == [
            ("fanbox", "1", "First"),
            ("patreon", "2", "Other"),
        ]

    def test_fetch_old_site_favorites_paginates_then_stops(self, monkeypatch):
        pages = {
            0: [{"id": "1", "service": "fanbox", "name": "A"}],
            50: [],
        }

        class FakeSession:
            def get(self, url, headers=None, timeout=None):
                if "o=0" in url:
                    payload = pages[0]
                else:
                    payload = pages[50]

                class FakeResponse:
                    status_code = 200
                    content = b"[]"

                    def raise_for_status(self):
                        return None

                    def json(self):
                        return payload

                return FakeResponse()

        monkeypatch.setattr(pawchive.time, "sleep", lambda *_: None)
        entries = pawchive.fetch_old_site_favorites(
            "kemono.su", "session=abc", session=FakeSession(), page_size=50
        )
        assert entries == [("fanbox", "1", "A")]
