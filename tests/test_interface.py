"""Tests for smooth._interface."""

import asyncio
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
  TaskHandleEx,
)
from smooth._tools import SmoothTool
from smooth.models import BrowserSessionResponse, TaskEvent, TaskResponse, ToolSignature


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

  # --- Poller event processing ---

  async def test_poller_dispatches_tool_call(self):
    """Poller must handle tool_call events whose payload has name+input keys
    (matching SessionActionPayload schema) without AttributeError."""
    client = self._make_client()
    call_count = 0
    tool_called_with = {}

    async def mock_tool(task_handle, event_id, **kwargs):
      tool_called_with.update(kwargs)

    tool = AsyncMock(side_effect=mock_tool)
    tool.name = "my_tool"

    handle = AsyncTaskHandle("t-1", client, tools=[tool])
    handle._poll_interval = 0.05

    async def mock_get_task(task_id, query_params=None):
      nonlocal call_count
      call_count += 1
      if call_count == 1:
        return TaskResponse(id="t-1", status="running")
      if call_count == 2:
        return TaskResponse(
          id="t-1",
          status="running",
          events=[
            TaskEvent(
              name="tool_call",
              payload={"name": "my_tool", "input": {"x": 42}},
              id="ev-1",
              timestamp=1,
            )
          ],
        )
      return TaskResponse(id="t-1", status="done", output="ok")

    client._get_task = mock_get_task
    result = await handle.result(timeout=5)
    assert result.status == "done"
    tool.assert_called_once()
    assert tool_called_with == {"x": 42}

  async def test_poller_resolves_browser_action_future(self):
    """Poller must resolve futures for browser_action response events."""
    client = self._make_client()
    call_count = 0

    handle = AsyncTaskHandle("t-1", client)
    handle._poll_interval = 0.05

    future = asyncio.get_running_loop().create_future()
    handle._event_futures["ev-1"] = future

    async def mock_get_task(task_id, query_params=None):
      nonlocal call_count
      call_count += 1
      if call_count <= 1:
        return TaskResponse(id="t-1", status="running")
      if call_count == 2:
        return TaskResponse(
          id="t-1",
          status="running",
          events=[
            TaskEvent(
              name="browser_action",
              payload={"code": 200, "output": "action result"},
              id="ev-1",
              timestamp=1,
            )
          ],
        )
      return TaskResponse(id="t-1", status="done")

    client._get_task = mock_get_task

    async with handle._connection():
      result = await asyncio.wait_for(future, timeout=5)

    assert result == "action result"


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

  async def test_run_task_passes_secret_str_through(self):
    """SecretStr values passed to run_task must be kept as SecretStr in the event payload
    so that _dump_json can reveal them at the serialization boundary."""
    from pydantic import SecretStr

    handle = self._make_handle()

    with patch.object(
      handle, "_send_event", return_value={"status": "running", "credits_used": 0, "duration": 0, "output": None}
    ) as mock_send:
      await handle.run_task(
        task="login",
        secrets={"https://example.com/*": {"password": SecretStr("SuperSecret123")}},
      )

      event = mock_send.call_args[0][0]
      sent_secret = event.payload.input.secrets["https://example.com/*"]["password"]
      assert isinstance(sent_secret, SecretStr), f"Expected SecretStr, got: {type(sent_secret)}"
      assert sent_secret.get_secret_value() == "SuperSecret123"


# --- SessionHandle (sync) ---


class TestSessionHandle:
  def test_init_shares_inner_async_handle(self):
    """SessionHandle must share the same AsyncTaskHandle between sync and async paths."""
    client = MagicMock()
    client._async_client = AsyncMock()
    client._async_client._get_task = AsyncMock(return_value=TaskResponse(id="t-1", status="running"))
    client._loop = asyncio.new_event_loop()

    handle = SessionHandle("t-1", client)

    # The sync TaskHandle and AsyncSessionHandle must share the same inner AsyncTaskHandle
    assert handle._handle._async_handle is handle._async_handle._handle

  def test_init_task_handle_links_to_sync_handle(self):
    """The inner AsyncTaskHandle's _task_handle must be the sync TaskHandle."""
    client = MagicMock()
    client._async_client = AsyncMock()
    client._async_client._get_task = AsyncMock(return_value=TaskResponse(id="t-1", status="running"))
    client._loop = asyncio.new_event_loop()

    handle = SessionHandle("t-1", client)

    inner_async_handle = handle._async_handle._handle
    assert inner_async_handle._task_handle is handle._handle

  def test_smooth_tool_receives_sync_handle(self):
    """When the poller calls a SmoothTool, it must pass a TaskHandle (not AsyncTaskHandle)."""
    client = MagicMock()
    client._async_client = AsyncMock()
    client._async_client._get_task = AsyncMock(return_value=TaskResponse(id="t-1", status="running"))
    client._loop = asyncio.new_event_loop()

    def my_tool(x: str):
      return f"got {x}"

    tool = SmoothTool(
      signature=ToolSignature(name="my_tool", description="test", inputs={"x": {"type": "string"}}, output="string"),
      fn=my_tool,
      essential=True,
    )
    handle = SessionHandle("t-1", client, tools=[tool])

    # The _task_handle that the poller passes to tools must be a TaskHandle
    inner_async_handle = handle._async_handle._handle
    assert isinstance(inner_async_handle._task_handle, TaskHandle)


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
