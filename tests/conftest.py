"""Shared fixtures for Smooth SDK tests."""

import os
from unittest.mock import patch

import pytest

FAKE_API_KEY = "cmzr-test-key-0123456789abcdef"


@pytest.fixture(autouse=True)
def _disable_telemetry(monkeypatch):
  """Disable telemetry globally for all tests."""
  monkeypatch.setenv("SMOOTH_TELEMETRY", "off")


@pytest.fixture()
def fake_api_key():
  """Return a fake API key for tests."""
  return FAKE_API_KEY


@pytest.fixture()
def mock_env_api_key(monkeypatch):
  """Set CIRCLEMIND_API_KEY in the environment."""
  monkeypatch.setenv("CIRCLEMIND_API_KEY", FAKE_API_KEY)
  return FAKE_API_KEY


@pytest.fixture()
def tmp_smooth_dir(tmp_path, monkeypatch):
  """Redirect ~/.smooth/ config and session paths to a temp directory."""
  smooth_dir = tmp_path / ".smooth"
  smooth_dir.mkdir()
  monkeypatch.setattr("smooth.cli.get_config_path", lambda: smooth_dir / "config.json")
  monkeypatch.setattr("smooth.cli.get_sessions_path", lambda: smooth_dir / "sessions.json")
  return smooth_dir
