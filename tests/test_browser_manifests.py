import json
import os


def load_manifest(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_chrome_manifest_is_mv3():
    path = os.path.join("browser-extension", "chrome_manifest.json")
    m = load_manifest(path)
    assert m.get("manifest_version") == 3
    assert "service_worker" in m.get("background", {})


def test_firefox_manifest_is_mv2():
    path = os.path.join("browser-extension", "firefox_manifest.json")
    m = load_manifest(path)
    assert m.get("manifest_version") == 2
    assert "scripts" in m.get("background", {}) or m.get("applications")


def _assert_pawchive_hosts(manifest):
    blob = json.dumps(manifest)
    assert "pawchive.pw" in blob


def test_chrome_manifest_includes_pawchive():
    path = os.path.join("browser-extension", "chrome_manifest.json")
    _assert_pawchive_hosts(load_manifest(path))


def test_firefox_manifest_includes_pawchive():
    path = os.path.join("browser-extension", "firefox_manifest.json")
    _assert_pawchive_hosts(load_manifest(path))


def test_manifest_json_is_usable_chrome_copy():
    path = os.path.join("browser-extension", "manifest.json")
    m = load_manifest(path)
    assert m.get("manifest_version") == 3
    assert m.get("version") != "0.0.0"
    assert "service_worker" in m.get("background", {})
    _assert_pawchive_hosts(m)
