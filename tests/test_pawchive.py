"""Tests for the Pawchive / Kemono-family favorites helpers (no Qt required)."""

import json

import pytest

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
        text = json.dumps([{"id": "77", "service": "fanbox", "name": "X"}])
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


@pytest.fixture
def fast_pacer(monkeypatch):
    """Disable real 1-rps pacing; the pacer itself is tested elsewhere."""
    monkeypatch.setattr(
        pawchive,
        "pace_pawchive_request",
        lambda url, is_running=None, interval=1.0: True,
    )


def _fake_time(monkeypatch, sleeps):
    """Patch only ``pawchive.time`` so other modules keep the real clock."""

    class _Time:
        @staticmethod
        def sleep(seconds):
            sleeps.append(seconds)

        @staticmethod
        def monotonic():
            return 0.0

    monkeypatch.setattr(pawchive, "time", _Time)


class TestRequestJson:
    """Every metadata call must be paced and Retry-After aware."""

    @pytest.fixture(autouse=True)
    def _fixtures(self, fast_pacer):
        # Every test here goes through the JSON helper, never the real pacer.
        yield

    class _Response:
        def __init__(self, status=200, payload=None, headers=None):
            self.status_code = status
            self._payload = payload
            self.headers = headers or {}
            self.content = b"[]" if payload is not None else b""

        def json(self):
            return self._payload

        def raise_for_status(self):
            if self.status_code >= 400:
                import requests

                raise requests.HTTPError(f"HTTP {self.status_code}")

    class _Session:
        def __init__(self, responses):
            self._responses = list(responses)
            self.calls = []

        def get(self, url, headers=None, timeout=None):
            self.calls.append((url, headers))
            return self._responses.pop(0)

    def test_parses_bare_array(self):
        session = self._Session([self._Response(200, [{"a": 1}])])
        assert pawchive._request_json(session, "https://pawchive.pw/api/v1/posts") == [
            {"a": 1}
        ]

    def test_empty_body_is_none(self):
        session = self._Session([self._Response(200, None)])
        assert (
            pawchive._request_json(session, "https://pawchive.pw/api/v1/posts") is None
        )

    def test_retries_429_using_retry_after(self, monkeypatch):
        slept = []
        _fake_time(monkeypatch, slept)
        session = self._Session(
            [
                self._Response(429, None, {"Retry-After": "7"}),
                self._Response(200, [{"a": 2}]),
            ]
        )
        payload = pawchive._request_json(session, "https://pawchive.pw/api/v1/posts")
        assert payload == [{"a": 2}]
        assert slept == [7.0]
        assert len(session.calls) == 2

    def test_gives_up_after_max_attempts(self, monkeypatch):
        import pytest
        import requests

        _fake_time(monkeypatch, [])
        session = self._Session([self._Response(503) for _ in range(3)])
        with pytest.raises(requests.HTTPError):
            pawchive._request_json(
                session, "https://pawchive.pw/api/v1/posts", max_attempts=2
            )
        assert len(session.calls) == 2

    def test_cancellation_before_request(self):
        import pytest
        import requests

        session = self._Session([self._Response(200, [])])
        with pytest.raises(requests.RequestException):
            pawchive._request_json(
                session, "https://pawchive.pw/api/v1/posts", is_running=lambda: False
            )
        assert session.calls == []

    def test_browser_impersonation_avoided(self):
        session = self._Session([self._Response(200, [])])
        pawchive._request_json(session, "https://pawchive.pw/api/v1/posts")
        headers = session.calls[0][1]
        assert "Mozilla" not in headers.get("User-Agent", "")
        assert "KemonoDownloader/" in headers["User-Agent"]


class TestExtractPosts:
    def test_bare_array(self):
        assert pawchive.extract_posts([{"id": 1}]) == [{"id": 1}]

    def test_kemono_envelope(self):
        payload = {"count": 1, "true_count": 1, "posts": [{"id": 2}]}
        assert pawchive.extract_posts(payload) == [{"id": 2}]

    def test_data_and_results_envelopes(self):
        assert pawchive.extract_posts({"data": [{"id": 3}]}) == [{"id": 3}]
        assert pawchive.extract_posts({"results": [{"id": 4}]}) == [{"id": 4}]

    def test_drops_non_dicts_and_garbage(self):
        assert pawchive.extract_posts([{"id": 1}, "x", None]) == [{"id": 1}]
        assert pawchive.extract_posts({}) == []
        assert pawchive.extract_posts(None) == []


class TestFetchFavoritesType:
    def test_requests_artist_type(self, monkeypatch):
        seen = {}

        def fake_request(session, url, **kwargs):
            seen["url"] = url
            return []

        monkeypatch.setattr(pawchive, "_request_json", fake_request)
        pawchive.fetch_favorites(domain="pawchive.pw", session=object())
        assert seen["url"] == "https://pawchive.pw/api/v1/account/favorites?type=artist"

    def test_post_type(self, monkeypatch):
        seen = {}

        def fake_request(session, url, **kwargs):
            seen["url"] = url
            return []

        monkeypatch.setattr(pawchive, "_request_json", fake_request)
        pawchive.fetch_favorites(
            domain="pawchive.pw", session=object(), fav_type="post"
        )
        assert seen["url"].endswith("?type=post")


class TestSessionHelpers:
    class _Cookies(dict):
        pass

    def test_extract_session_cookie(self):
        session = type("S", (), {"cookies": {"session": "abc"}})()
        assert pawchive.extract_session_cookie(session) == "abc"

    def test_extract_missing_cookie(self):
        assert pawchive.extract_session_cookie(type("S", (), {"cookies": {}})()) == ""
        assert pawchive.extract_session_cookie(object()) == ""
        assert pawchive.extract_session_cookie(None) == ""


class TestLoginWithPassword:
    class _Session:
        def __init__(self, cookies, status=200):
            self.cookies = cookies
            self.status = status
            self.posts = []

        def post(
            self, url, data=None, headers=None, timeout=None, allow_redirects=True
        ):
            self.posts.append((url, data, headers))
            return type("R", (), {"status_code": self.status})()

    def test_returns_cookie(self):
        session = self._Session({"session": "tok"})
        token = pawchive.login_with_password(
            "u", "p", domain="pawchive.pw", session=session
        )
        assert token == "tok"
        assert session.posts[0][0] == "https://pawchive.pw/account/login"
        assert session.posts[0][1] == {"username": "u", "password": "p"}
        assert (
            session.posts[0][2]["Content-Type"] == "application/x-www-form-urlencoded"
        )

    def test_missing_cookie_raises(self):
        import pytest

        session = self._Session({})
        with pytest.raises(pawchive.PawchiveLoginError):
            pawchive.login_with_password(
                "u", "p", domain="pawchive.pw", session=session
            )

    def test_blank_credentials_raise_without_request(self):
        import pytest

        session = self._Session({"session": "tok"})
        for username, password in (("", "p"), ("u", ""), ("  ", " ")):
            with pytest.raises(pawchive.PawchiveLoginError):
                pawchive.login_with_password(
                    username, password, domain="pawchive.pw", session=session
                )
        assert session.posts == []

    def test_cancelled_login(self):
        import pytest

        session = self._Session({"session": "tok"})
        with pytest.raises(pawchive.PawchiveLoginError):
            pawchive.login_with_password(
                "u",
                "p",
                domain="pawchive.pw",
                session=session,
                is_running=lambda: False,
            )
        assert session.posts == []


class TestVerifySession:
    class _Session:
        def __init__(self, status, payload):
            self.status = status
            self.payload = payload
            self.calls = []

        def get(self, url, headers=None, timeout=None):
            self.calls.append((url, headers))
            response = type("R", (), {})()
            response.status_code = self.status
            response.json = lambda: self.payload
            return response

    def test_empty_credential_is_false_without_request(self):
        session = self._Session(200, [])
        assert (
            pawchive.verify_session("", domain="pawchive.pw", session=session) is False
        )
        assert session.calls == []

    def test_401_is_false(self):
        session = self._Session(401, {})
        assert (
            pawchive.verify_session("tok", domain="pawchive.pw", session=session)
            is False
        )

    def test_empty_object_is_false(self):
        session = self._Session(200, {})
        assert (
            pawchive.verify_session("tok", domain="pawchive.pw", session=session)
            is False
        )

    def test_favorites_payload_is_true(self):
        session = self._Session(200, [{"id": "1", "service": "patreon"}])
        assert (
            pawchive.verify_session("tok", domain="pawchive.pw", session=session)
            is True
        )
        assert session.calls[0][1]["Cookie"] == "session=tok"

    def test_server_error_is_false(self):
        session = self._Session(502, [])
        assert (
            pawchive.verify_session("tok", domain="pawchive.pw", session=session)
            is False
        )


class TestFileSizeCapAlias:
    def test_matches_shared_helper(self):
        from kemonodownloader import pawchive_files

        assert pawchive.file_size_cap_for_favorites(0) == pawchive_files.size_cap_bytes(
            0
        )
        assert pawchive.file_size_cap_for_favorites(
            6000
        ) == pawchive_files.size_cap_bytes(6000)
