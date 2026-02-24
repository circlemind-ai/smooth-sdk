"""Tests for smooth._interface."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from smooth._exceptions import ApiError, BadRequestError
from smooth._interface import (
  AsyncSessionHandle,
  AsyncTaskHandle,
  AsyncTaskHandleEx,
  BaseTaskHandle,
  BrowserSessionHandle,
  SessionHandle,
  TaskHandle,
)
from smooth.models import BrowserSessionResponse, TaskEvent, TaskResponse


FAKE_KEY = "cmzr-test-key-0123456789abcdef"


# --- BaseTaskHandle ---


class TestBaseTaskHandle:
  def test_id(self):
    handle = BaseTaskHandle("t-123")
    assert handle.id() == "t-123"
    assert handle._id == "t-123"


# --- AsyncTaskHandle ---


class TestAsyncTaskHandle:
  def _make_client(self):
    client = AsyncMock()
    client._get_task = AsyncMock()
    client._delete_task = AsyncMock()
    client._send_task_event = AsyncMock()
    return client

  def test_init(self):
    client = self._make_client()
    handle = AsyncTaskHandle("t-1", client)
    assert handle.id() == "t-1"
    assert handle._tools == {}
    assert handle._is_alive == 0

  async def test_result_returns_cached_terminal_response(self):
    client = self._make_client()
    handle = AsyncTaskHandle("t-1", client)
    handle._task_response = TaskResponse(id="t-1", status="done", output="hello")
    result = await handle.result()
    assert result.output == "hello"
    client._get_task.assert_not_called()

  async def test_result_raises_on_invalid_timeout(self):
    client = self._make_client()
    handle = AsyncTaskHandle("t-1", client)
    with pytest.raises(ValueError, match="Timeout must be at least 1"):
      await handle.result(timeout=0)

  async def test_result_polls_until_done(self):
    client = self._make_client()
    call_count = 0

    async def mock_get_task(task_id, query_params=None):
      nonlocal call_count
      call_count += 1
      if call_count <= 2:
        return TaskResponse(id="t-1", status="running")
      return TaskResponse(id="t-1", status="done", output="final")

    client._get_task = mock_get_task
    handle = AsyncTaskHandle("t-1", client)
    handle._poll_interval = 0.1

    result = await handle.result(timeout=5)
    assert result.status == "done"
    assert result.output == "final"

  async def test_result_raises_timeout_when_task_never_completes(self):
    client = self._make_client()

    async def always_running(task_id, query_params=None):
      return TaskResponse(id="t-1", status="running")

    client._get_task = always_running
    handle = AsyncTaskHandle("t-1", client)
    handle._poll_interval = 0.1

    with pytest.raises(TimeoutError, match="did not complete within"):
      await handle.result(timeout=1)

  async def test_live_url_raises_when_not_running(self):
    client = self._make_client()
    handle = AsyncTaskHandle("t-1", client)
    handle._task_response = TaskResponse(id="t-1", status="done")

    with pytest.raises(BadRequestError, match="Live URL not available"):
      await handle.live_url()

  async def test_live_url_returns_when_available(self):
    client = self._make_client()
    handle = AsyncTaskHandle("t-1", client)
    handle._task_response = TaskResponse(id="t-1", status="running", live_url="https://live.example.com/view")

    url = await handle.live_url()
    assert "live.example.com" in url
    assert "interactive=true" in url

  async def test_recording_url_returns_cached(self):
    client = self._make_client()
    handle = AsyncTaskHandle("t-1", client)
    handle._task_response = TaskResponse(id="t-1", status="done", recording_url="https://rec.example.com")

    url = await handle.recording_url()
    assert url == "https://rec.example.com"

  async def test_recording_url_raises_when_empty(self):
    client = self._make_client()
    call_count = 0

    async def mock_get_task(task_id, query_params=None):
      nonlocal call_count
      call_count += 1
      if call_count <= 1:
        return TaskResponse(id="t-1", status="running")
      return TaskResponse(id="t-1", status="done", recording_url="")

    client._get_task = mock_get_task
    handle = AsyncTaskHandle("t-1", client)
    handle._poll_interval = 0.1

    with pytest.raises(ApiError, match="Recording URL not available"):
      await handle.recording_url(timeout=2)

  # --- Proxy ---

  def test_start_proxy(self):
    client = self._make_client()
    handle = AsyncTaskHandle("t-1", client)

    with patch("smooth._interface.FRPProxy") as MockProxy:
      mock_instance = MagicMock()
      MockProxy.return_value = mock_instance

      handle._start_proxy("proxy.example.com", "token123")

      MockProxy.assert_called_once()
      mock_instance.start.assert_called_once()
      assert handle._proxy is mock_instance

  def test_start_proxy_raises_if_already_running(self):
    client = self._make_client()
    handle = AsyncTaskHandle("t-1", client)
    handle._proxy = MagicMock()
    handle._proxy.is_running = True

    with pytest.raises(RuntimeError, match="already running"):
      handle._start_proxy("proxy.example.com", "token")

  def test_stop_proxy(self):
    client = self._make_client()
    handle = AsyncTaskHandle("t-1", client)
    mock_proxy = MagicMock()
    handle._proxy = mock_proxy

    handle._stop_proxy()
    mock_proxy.stop.assert_called_once()
    assert handle._proxy is None

  def test_has_proxy(self):
    client = self._make_client()
    handle = AsyncTaskHandle("t-1", client)
    assert handle._has_proxy is False

    handle._proxy = MagicMock()
    handle._proxy.is_running = True
    assert handle._has_proxy is True

  # --- Connection ---

  def test_disconnect_decrements_alive(self):
    client = self._make_client()
    handle = AsyncTaskHandle("t-1", client)
    handle._is_alive = 2
    handle._disconnect()
    assert handle._is_alive == 1

  def test_disconnect_force(self):
    client = self._make_client()
    handle = AsyncTaskHandle("t-1", client)
    handle._is_alive = 1
    handle._task_response = TaskResponse(id="t-1", status="running")
    handle._disconnect(force=True)
    assert handle._task_response.status == "cancelled"


# --- AsyncTaskHandleEx ---


class TestAsyncTaskHandleEx:
  def _make_handle(self):
    client = AsyncMock()
    client._send_task_event = AsyncMock(return_value=MagicMock(id="resp-1"))
    handle = AsyncTaskHandle("t-1", client)
    return AsyncTaskHandleEx(handle)

  async def test_goto_sends_correct_event(self):
    ex = self._make_handle()

    with patch.object(ex, "_send_event", return_value={"credits_used": 0, "duration": 0}) as mock_send:
      result = await ex.goto("https://example.com")
      mock_send.assert_called_once()
      event = mock_send.call_args[0][0]
      assert event.name == "browser_action"
      assert event.payload["name"] == "goto"
      assert event.payload["input"]["url"] == "https://example.com"

  async def test_extract_sends_correct_event(self):
    ex = self._make_handle()

    with patch.object(ex, "_send_event", return_value={"output": {"name": "John"}, "credits_used": 1, "duration": 0.5}) as mock_send:
      result = await ex.extract(schema={"name": "string"}, prompt="get the name")
      event = mock_send.call_args[0][0]
      assert event.name == "browser_action"
      assert event.payload["name"] == "extract"
      assert event.payload["input"]["schema"] == {"name": "string"}
      assert event.payload["input"]["prompt"] == "get the name"

  async def test_evaluate_js_sends_correct_event(self):
    ex = self._make_handle()

    with patch.object(ex, "_send_event", return_value={"output": 42, "credits_used": 0, "duration": 0}) as mock_send:
      result = await ex.evaluate_js("return 1+1", args={"x": 10})
      event = mock_send.call_args[0][0]
      assert event.name == "browser_action"
      assert event.payload["name"] == "evaluate_js"
      assert event.payload["input"]["js"] == "return 1+1"
      assert event.payload["input"]["args"] == {"x": 10}


# --- AsyncSessionHandle ---


class TestAsyncSessionHandle:
  def _make_handle(self):
    client = AsyncMock()
    client._delete_task = AsyncMock()
    client._get_task = AsyncMock(return_value=TaskResponse(id="t-1", status="running"))
    return AsyncSessionHandle("t-1", client)

  async def test_close_force_deletes_task(self):
    handle = self._make_handle()
    result = await handle.close(force=True)
    handle._client._delete_task.assert_called_once_with("t-1")
    assert result is True

  async def test_close_graceful_sends_close_event(self):
    handle = self._make_handle()

    with patch.object(handle, "_send_event", return_value={"output": True, "credits_used": 5, "duration": 1.0}) as mock_send:
      result = await handle.close(force=False)
      assert result is True
      event = mock_send.call_args[0][0]
      assert event.name == "session_action"
      assert event.payload["name"] == "close"

  async def test_close_graceful_runtime_error_fallback(self):
    """When the poller stops (RuntimeError), close still succeeds."""
    handle = self._make_handle()

    with patch.object(handle, "_send_event", side_effect=RuntimeError("poller stopped")):
      result = await handle.close(force=False)
      assert result is True

  async def test_result_raises_if_not_closed(self):
    handle = self._make_handle()
    with pytest.raises(BadRequestError, match="result\\(\\) cannot be called on an open session"):
      await handle.result()


# --- BrowserSessionHandle (deprecated) ---


class TestBrowserSessionHandle:
  def test_profile_id(self):
    resp = BrowserSessionResponse(profile_id="p-1", live_id="l-1", live_url="https://live.example.com")
    handle = BrowserSessionHandle(browser_session=resp)
    assert handle.profile_id() == "p-1"

  def test_live_url(self):
    resp = BrowserSessionResponse(profile_id="p-1", live_url="https://live.example.com/view")
    handle = BrowserSessionHandle(browser_session=resp)
    url = handle.live_url()
    assert url is not None
    assert "interactive=true" in url

  def test_live_url_none(self):
    resp = BrowserSessionResponse(profile_id="p-1", live_url=None)
    handle = BrowserSessionHandle(browser_session=resp)
    assert handle.live_url() is None

  def test_live_id(self):
    resp = BrowserSessionResponse(profile_id="p-1", live_id="lid-1")
    handle = BrowserSessionHandle(browser_session=resp)
    assert handle.live_id() == "lid-1"
