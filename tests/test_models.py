"""Tests for smooth.models."""

import warnings

import pytest
from pydantic import ValidationError

from smooth.models import (
  BrowserProfilesResponse,
  BrowserSessionRequest,
  BrowserSessionResponse,
  TaskEvent,
  TaskRequest,
  TaskResponse,
  ToolSignature,
)


# --- TaskRequest ---


class TestTaskRequest:
  def test_defaults(self):
    req = TaskRequest(task="do something")
    assert req.task == "do something"
    assert req.agent == "smooth"
    assert req.max_steps == 32
    assert req.device == "desktop"
    assert req.enable_recording is True
    assert req.stealth_mode is False
    assert req.use_adblock is True
    assert req.use_captcha_solver is True
    assert req.show_cursor is False

  def test_max_steps_validation_min(self):
    with pytest.raises(ValidationError):
      TaskRequest(task="x", max_steps=1)

  def test_max_steps_validation_max(self):
    with pytest.raises(ValidationError):
      TaskRequest(task="x", max_steps=200)

  def test_deprecated_session_id_migration(self):
    with warnings.catch_warnings():
      warnings.simplefilter("ignore", DeprecationWarning)
      req = TaskRequest.model_validate({"task": "x", "session_id": "sid-123"})
      assert req.profile_id == "sid-123"

  def test_profile_id_takes_precedence_over_session_id(self):
    """When both are provided, profile_id is used (session_id migration is skipped)."""
    req = TaskRequest(task="x", profile_id="pid-1")
    assert req.profile_id == "pid-1"

  def test_model_dump_includes_session_id(self):
    req = TaskRequest(task="x", profile_id="pid-1")
    data = req.model_dump()
    assert data["profile_id"] == "pid-1"
    assert data["session_id"] == "pid-1"

  def test_none_task_allowed(self):
    req = TaskRequest(task=None)
    assert req.task is None

  def test_extra_fields_allowed(self):
    req = TaskRequest(task="x", some_future_field="hello")
    assert req.model_dump()["some_future_field"] == "hello"


# --- TaskResponse ---


class TestTaskResponse:
  def test_minimal(self):
    resp = TaskResponse(id="t-1", status="running")
    assert resp.id == "t-1"
    assert resp.status == "running"
    assert resp.output is None
    assert resp.live_url is None

  @pytest.mark.parametrize("status", ["waiting", "running", "done", "failed", "cancelled"])
  def test_all_statuses(self, status):
    resp = TaskResponse(id="t-1", status=status)
    assert resp.status == status

  def test_with_all_fields(self):
    resp = TaskResponse(
      id="t-1",
      status="done",
      output={"key": "value"},
      credits_used=10,
      device="mobile",
      live_url="https://live.example.com",
      recording_url="https://rec.example.com",
      downloads_url="https://dl.example.com",
      created_at=1700000000,
    )
    assert resp.output == {"key": "value"}
    assert resp.credits_used == 10
    assert resp.device == "mobile"


# --- Deprecated field migration ---


class TestDeprecatedSessionIdMigration:
  """Test session_id -> profile_id migration across models that share this pattern."""

  def test_browser_session_request_session_id_migrates(self):
    with warnings.catch_warnings():
      warnings.simplefilter("ignore", DeprecationWarning)
      obj = BrowserSessionRequest.model_validate({"session_id": "sid-old"})
      assert obj.profile_id == "sid-old"

  def test_browser_session_response_session_id_migrates(self):
    with warnings.catch_warnings():
      warnings.simplefilter("ignore", DeprecationWarning)
      obj = BrowserSessionResponse.model_validate({"session_id": "sid-old"})
      assert obj.profile_id == "sid-old"

  def test_browser_profiles_response_session_ids_migration(self):
    with warnings.catch_warnings():
      warnings.simplefilter("ignore", DeprecationWarning)
      resp = BrowserProfilesResponse.model_validate({"session_ids": ["a", "b"]})
      assert resp.profile_ids == ["a", "b"]

  def test_browser_profiles_response_model_dump(self):
    resp = BrowserProfilesResponse(profile_ids=["a", "b"])
    data = resp.model_dump()
    assert data["profile_ids"] == ["a", "b"]
    assert data["session_ids"] == ["a", "b"]


# --- Models with non-trivial schema ---


class TestModelsWithLogic:
  def test_tool_signature_fields(self):
    sig = ToolSignature(name="my_tool", description="does stuff", inputs={"a": "string"}, output="result")
    assert sig.name == "my_tool"
    assert sig.inputs == {"a": "string"}

  def test_task_event_optional_fields(self):
    event = TaskEvent(name="tool_call", payload={"name": "click"})
    assert event.id is None
    assert event.timestamp is None

    event2 = TaskEvent(name="tool_call", payload={}, id="e-1", timestamp=123)
    assert event2.id == "e-1"
    assert event2.timestamp == 123
