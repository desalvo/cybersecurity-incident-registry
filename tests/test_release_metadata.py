import importlib


def test_release_metadata_files_match_defaults(monkeypatch):
    monkeypatch.delenv("APP_VERSION", raising=False)
    monkeypatch.delenv("APP_BUILD", raising=False)
    import app.version as release
    release = importlib.reload(release)
    assert release.APP_RELEASE_VERSION == "0.8.0-1"
    assert release.APP_RELEASE_BUILD == "20260718"


def test_release_metadata_supports_environment_override(monkeypatch):
    import app.version as release
    monkeypatch.setenv("APP_VERSION", "9.9.9-test")
    monkeypatch.setenv("APP_BUILD", "test-build")
    release = importlib.reload(release)
    assert release.APP_RELEASE_VERSION == "9.9.9-test"
    assert release.APP_RELEASE_BUILD == "test-build"
    monkeypatch.delenv("APP_VERSION")
    monkeypatch.delenv("APP_BUILD")
    release = importlib.reload(release)
    assert release.APP_RELEASE_VERSION == "0.8.0-1"
    assert release.APP_RELEASE_BUILD == "20260718"
