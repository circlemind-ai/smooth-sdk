"""Tests for smooth.cli."""

import json
from unittest.mock import patch

import pytest

from smooth.cli import (
  add_session,
  config_command,
  get_session,
  kill_proxy_process,
  load_config,
  load_config_to_env,
  load_sessions,
  print_error_json,
  print_json,
  print_success,
  remove_session,
  save_config,
  save_sessions,
  update_session_task,
)

# --- Pure functions ---


class TestPrintJson:
  def test_outputs_formatted_json(self, capsys):
    print_json({"key": "value"})
    output = capsys.readouterr().out
    parsed = json.loads(output)
    assert parsed == {"key": "value"}


class TestPrintSuccess:
  def test_success_with_message(self, capsys):
    print_success("Done!", {"id": "123"})
    output = capsys.readouterr().out
    parsed = json.loads(output)
    assert parsed["success"] is True
    assert parsed["message"] == "Done!"
    assert parsed["id"] == "123"

  def test_success_without_data(self, capsys):
    print_success("OK")
    output = capsys.readouterr().out
    parsed = json.loads(output)
    assert parsed["success"] is True
    assert "id" not in parsed


class TestPrintErrorJson:
  def test_outputs_to_stderr_and_exits(self, capsys):
    with pytest.raises(SystemExit) as exc_info:
      print_error_json("something went wrong")
    assert exc_info.value.code == 1
    output = capsys.readouterr().err
    parsed = json.loads(output)
    assert parsed["success"] is False
    assert parsed["error"] == "something went wrong"


# --- Config file management ---


class TestConfigManagement:
  def test_save_and_load_config(self, tmp_smooth_dir):
    save_config({"api_key": "test-key"})
    config = load_config()
    assert config["api_key"] == "test-key"

  def test_load_config_missing_file(self, tmp_smooth_dir):
    config = load_config()
    assert config == {}

  def test_load_config_invalid_json(self, tmp_smooth_dir):
    config_path = tmp_smooth_dir / "config.json"
    config_path.write_text("not json!!!")
    config = load_config()
    assert config == {}

  def test_load_config_to_env_sets_key(self, tmp_smooth_dir, monkeypatch):
    monkeypatch.delenv("CIRCLEMIND_API_KEY", raising=False)
    save_config({"api_key": "from-config"})
    load_config_to_env()
    import os

    assert os.environ.get("CIRCLEMIND_API_KEY") == "from-config"

  def test_load_config_to_env_does_not_override(self, tmp_smooth_dir, monkeypatch):
    monkeypatch.setenv("CIRCLEMIND_API_KEY", "from-env")
    save_config({"api_key": "from-config"})
    load_config_to_env()
    import os

    assert os.environ.get("CIRCLEMIND_API_KEY") == "from-env"


# --- Session file management ---


class TestSessionManagement:
  def test_save_and_load_sessions(self, tmp_smooth_dir):
    save_sessions({"sessions": [{"session_id": "s1"}]})
    data = load_sessions()
    assert len(data["sessions"]) == 1
    assert data["sessions"][0]["session_id"] == "s1"

  def test_load_sessions_missing_file(self, tmp_smooth_dir):
    data = load_sessions()
    assert data == {"sessions": []}

  def test_load_sessions_invalid_json(self, tmp_smooth_dir):
    sessions_path = tmp_smooth_dir / "sessions.json"
    sessions_path.write_text("bad json")
    data = load_sessions()
    assert data == {"sessions": []}

  def test_add_session(self, tmp_smooth_dir):
    add_session("s1", "https://live.example.com", "desktop", task="my task")
    data = load_sessions()
    assert len(data["sessions"]) == 1
    s = data["sessions"][0]
    assert s["session_id"] == "s1"
    assert s["live_url"] == "https://live.example.com"
    assert s["device"] == "desktop"
    assert s["task"] == "my task"
    assert "start_time" in s

  def test_add_session_with_proxy_pid(self, tmp_smooth_dir):
    add_session("s1", None, "mobile", proxy_pid=12345)
    data = load_sessions()
    assert data["sessions"][0]["proxy_pid"] == "12345"

  def test_remove_session(self, tmp_smooth_dir):
    add_session("s1", None, "desktop")
    add_session("s2", None, "mobile")
    remove_session("s1")
    data = load_sessions()
    assert len(data["sessions"]) == 1
    assert data["sessions"][0]["session_id"] == "s2"

  def test_remove_nonexistent_session(self, tmp_smooth_dir):
    add_session("s1", None, "desktop")
    remove_session("nonexistent")
    data = load_sessions()
    assert len(data["sessions"]) == 1

  def test_update_session_task(self, tmp_smooth_dir):
    add_session("s1", None, "desktop", task="old task")
    update_session_task("s1", "new task")
    data = load_sessions()
    assert data["sessions"][0]["task"] == "new task"

  def test_update_session_task_to_none(self, tmp_smooth_dir):
    add_session("s1", None, "desktop", task="running")
    update_session_task("s1", None)
    data = load_sessions()
    assert data["sessions"][0]["task"] is None

  def test_get_session(self, tmp_smooth_dir):
    add_session("s1", "https://live.example.com", "desktop")
    session = get_session("s1")
    assert session is not None
    assert session["session_id"] == "s1"

  def test_get_session_not_found(self, tmp_smooth_dir):
    assert get_session("nonexistent") is None


# --- kill_proxy_process ---


class TestKillProxyProcess:
  def test_returns_true_on_success(self):
    with patch("os.kill") as mock_kill:
      assert kill_proxy_process(12345) is True
      mock_kill.assert_called_once()

  def test_returns_false_on_process_not_found(self):
    with patch("os.kill", side_effect=ProcessLookupError):
      assert kill_proxy_process(99999) is False

  def test_returns_false_on_permission_error(self):
    with patch("os.kill", side_effect=PermissionError):
      assert kill_proxy_process(1) is False

  def test_handles_string_pid(self):
    with patch("os.kill"):
      assert kill_proxy_process("12345") is True


# --- CLI argument parsing ---


class TestCliArgumentParsing:
  def test_main_no_args_shows_help(self, capsys):
    with patch("sys.argv", ["smooth"]):
      with pytest.raises(SystemExit) as exc_info:
        from smooth.cli import main

        main()
      assert exc_info.value.code == 1

  def test_config_command_saves_key(self, tmp_smooth_dir, capsys):
    import argparse

    args = argparse.Namespace(api_key="my-test-key", show=False, json=False)
    config_command(args)
    config = load_config()
    assert config["api_key"] == "my-test-key"

  def test_config_command_show(self, tmp_smooth_dir, capsys):
    import argparse

    save_config({"api_key": "cmzr-longkeyvaluehere1234567890"})
    args = argparse.Namespace(api_key=None, show=True, json=False)
    config_command(args)
    output = capsys.readouterr().out
    assert "..." in output  # Masked key

  def test_config_command_show_json(self, tmp_smooth_dir, capsys):
    import argparse

    save_config({"api_key": "my-key"})
    args = argparse.Namespace(api_key=None, show=True, json=True)
    config_command(args)
    output = capsys.readouterr().out
    parsed = json.loads(output)
    assert parsed["success"] is True
    assert "config" in parsed

  def test_config_rejects_placeholder_key(self, tmp_smooth_dir, capsys):
    import argparse

    args = argparse.Namespace(api_key="YOUR_API_KEY", show=False, json=False)
    with pytest.raises(SystemExit):
      config_command(args)
