"""Tests for credential loading."""

from __future__ import annotations

from pathlib import Path

import pytest

from groundskeeper.core.credentials import load_credentials


@pytest.fixture(autouse=True)
def _no_token_in_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GROUNDSKEEPER_GITHUB_TOKEN", raising=False)


@pytest.fixture
def credentials_file(tmp_path: Path) -> Path:
    path = tmp_path / "credentials.yaml"
    path.write_text("github:\n  token: from-file\n")
    return path


class TestLoadCredentials:
    def test_env_var_takes_precedence(
        self, credentials_file: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("GROUNDSKEEPER_GITHUB_TOKEN", "from-env")
        assert load_credentials("github", path=credentials_file) == {"token": "from-env"}

    def test_falls_back_to_credentials_file(self, credentials_file: Path):
        assert load_credentials("github", path=credentials_file) == {"token": "from-file"}

    def test_empty_env_var_is_ignored(
        self, credentials_file: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("GROUNDSKEEPER_GITHUB_TOKEN", "")
        assert load_credentials("github", path=credentials_file) == {"token": "from-file"}

    def test_reads_home_directory_by_default(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        (tmp_path / ".groundskeeper").mkdir()
        (tmp_path / ".groundskeeper" / "credentials.yaml").write_text("github:\n  token: home\n")
        assert load_credentials("github") == {"token": "home"}

    def test_platform_missing_from_file(self, tmp_path: Path):
        path = tmp_path / "credentials.yaml"
        path.write_text("slack:\n  token: xoxp-1\n")
        assert load_credentials("github", path=path) == {}

    def test_nothing_configured(self, tmp_path: Path):
        assert load_credentials("github", path=tmp_path / "missing.yaml") == {}
