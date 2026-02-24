"""Tests for smooth._proxy."""

import platform
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from smooth._proxy import FRP_DIR, FRPProxy, ProxyConfig, _ProxyState


def _make_config(**kwargs):
  defaults = {"server_url": "proxy.example.com", "token": "test-token", "session_id": "sess-1"}
  defaults.update(kwargs)
  return ProxyConfig(**defaults)


class TestProxyConfig:
  def test_defaults(self):
    config = ProxyConfig(server_url="x.com", token="tk")
    assert config.remote_port == 1080
    assert config.session_id == "default"

  def test_custom_values(self):
    config = ProxyConfig(server_url="x.com", token="tk", remote_port=9999, session_id="s-1")
    assert config.remote_port == 9999
    assert config.session_id == "s-1"


class TestGetPlatformInfo:
  def test_returns_three_element_tuple(self):
    os_name, arch, ext = FRPProxy._get_platform_info()
    assert os_name in ("linux", "darwin", "windows")
    assert arch in ("amd64", "arm64")
    assert ext in ("tar.gz", "zip")

  def test_windows_gets_zip(self):
    with patch("platform.system", return_value="Windows"):
      with patch("platform.machine", return_value="x86_64"):
        os_name, arch, ext = FRPProxy._get_platform_info()
        assert os_name == "windows"
        assert ext == "zip"

  def test_darwin_gets_tar(self):
    with patch("platform.system", return_value="Darwin"):
      with patch("platform.machine", return_value="arm64"):
        os_name, arch, ext = FRPProxy._get_platform_info()
        assert os_name == "darwin"
        assert arch == "arm64"
        assert ext == "tar.gz"

  def test_unsupported_arch_raises(self):
    with patch("platform.system", return_value="Linux"):
      with patch("platform.machine", return_value="mips"):
        with pytest.raises(RuntimeError, match="Unsupported architecture"):
          FRPProxy._get_platform_info()


class TestCreateConfig:
  def test_creates_yaml_file(self, tmp_path):
    config = _make_config()
    proxy = FRPProxy(config)

    with patch("smooth._proxy.FRP_DIR", tmp_path):
      path = proxy._create_config()
      assert path.exists()
      content = path.read_text()
      assert "proxy.example.com" in content
      assert "test-token" in content
      assert "sess-1" in content
      assert "socks5" in content

  def test_config_file_named_with_session_id(self, tmp_path):
    config = _make_config(session_id="my-session")
    proxy = FRPProxy(config)

    with patch("smooth._proxy.FRP_DIR", tmp_path):
      path = proxy._create_config()
      assert "my-session" in path.name


class TestFRPProxyLifecycle:
  def test_is_running_false_initially(self):
    proxy = FRPProxy(_make_config())
    assert proxy.is_running is False

  def test_is_running_true_when_process_alive(self):
    proxy = FRPProxy(_make_config())
    mock_process = MagicMock()
    mock_process.poll.return_value = None  # None means still running
    proxy._state.process = mock_process
    assert proxy.is_running is True

  def test_is_running_false_when_process_exited(self):
    proxy = FRPProxy(_make_config())
    mock_process = MagicMock()
    mock_process.poll.return_value = 0  # Exited
    proxy._state.process = mock_process
    assert proxy.is_running is False

  def test_start_raises_if_already_running(self):
    proxy = FRPProxy(_make_config())
    proxy._state.process = MagicMock()  # Already has a process

    with pytest.raises(RuntimeError, match="already running"):
      proxy.start()

  def test_cleanup_terminates_process(self, tmp_path):
    proxy = FRPProxy(_make_config())
    mock_process = MagicMock()
    mock_process.wait.return_value = 0
    proxy._state.process = mock_process

    config_file = tmp_path / "frpc_test.yml"
    config_file.write_text("test")
    proxy._state.config_file = config_file

    proxy._cleanup()

    mock_process.terminate.assert_called_once()
    assert proxy._state.process is None
    assert proxy._state.config_file is None
    assert not config_file.exists()

  def test_cleanup_kills_on_timeout(self, tmp_path):
    import subprocess

    proxy = FRPProxy(_make_config())
    mock_process = MagicMock()
    mock_process.wait.side_effect = [subprocess.TimeoutExpired("cmd", 5), 0]
    proxy._state.process = mock_process

    proxy._cleanup()

    mock_process.terminate.assert_called_once()
    mock_process.kill.assert_called_once()

  def test_stop_calls_cleanup(self):
    proxy = FRPProxy(_make_config())
    proxy._cleanup = MagicMock()
    proxy.stop()
    proxy._cleanup.assert_called_once()

  def test_context_manager(self):
    proxy = FRPProxy(_make_config())
    proxy.start = MagicMock()
    proxy.stop = MagicMock()

    with proxy:
      proxy.start.assert_called_once()
    proxy.stop.assert_called_once()
