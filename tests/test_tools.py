"""Tests for smooth._tools."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from smooth._exceptions import ToolCallError
from smooth._tools import AsyncSmoothTool, SmoothTool
from smooth.models import TaskEvent, ToolSignature


def _make_signature(name="test_tool"):
  return ToolSignature(name=name, description="A test tool", inputs={"x": "int"}, output="result")


class TestAsyncSmoothTool:
  def test_name_property(self):
    tool = AsyncSmoothTool(signature=_make_signature("my_tool"), fn=AsyncMock(), essential=True)
    assert tool.name == "my_tool"

  async def test_run_fn_passes_task_when_first_param_is_task(self):
    async def my_fn(task, x=1):
      return f"got task={type(task).__name__}, x={x}"

    tool = AsyncSmoothTool(signature=_make_signature(), fn=my_fn, essential=True)
    mock_task = MagicMock()
    result = await tool._run_fn(mock_task, x=42)
    assert "x=42" in result

  async def test_run_fn_omits_task_when_not_in_signature(self):
    async def my_fn(x=1):
      return f"x={x}"

    tool = AsyncSmoothTool(signature=_make_signature(), fn=my_fn, essential=True)
    mock_task = MagicMock()
    result = await tool._run_fn(mock_task, x=99)
    assert result == "x=99"

  async def test_handle_tool_response_success(self):
    tool = AsyncSmoothTool(signature=_make_signature(), fn=AsyncMock(), essential=True)
    mock_task = AsyncMock()
    mock_task._send_event = AsyncMock()

    await tool._handle_tool_response(mock_task, "e-1", "success result")

    mock_task._send_event.assert_called_once()
    event = mock_task._send_event.call_args[0][0]
    assert event.payload["code"] == 200
    assert event.payload["output"] == "success result"

  async def test_handle_tool_response_tool_call_error(self):
    tool = AsyncSmoothTool(signature=_make_signature(), fn=AsyncMock(), essential=True)
    mock_task = AsyncMock()
    mock_task._send_event = AsyncMock()

    await tool._handle_tool_response(mock_task, "e-1", ToolCallError("bad input"))

    event = mock_task._send_event.call_args[0][0]
    assert event.payload["code"] == 400

  async def test_handle_tool_response_essential_error_raises(self):
    tool = AsyncSmoothTool(signature=_make_signature(), fn=AsyncMock(), essential=True)
    mock_task = AsyncMock()
    mock_task._send_event = AsyncMock()

    with pytest.raises(RuntimeError, match="something broke"):
      await tool._handle_tool_response(mock_task, "e-1", RuntimeError("something broke"))

    event = mock_task._send_event.call_args[0][0]
    assert event.payload["code"] == 500

  async def test_handle_tool_response_non_essential_error_no_raise(self):
    tool = AsyncSmoothTool(signature=_make_signature(), fn=AsyncMock(), essential=False)
    mock_task = AsyncMock()
    mock_task._send_event = AsyncMock()

    # Should NOT raise for non-essential tool
    await tool._handle_tool_response(mock_task, "e-1", RuntimeError("minor issue"))

    event = mock_task._send_event.call_args[0][0]
    assert event.payload["code"] == 400

  async def test_handle_tool_response_custom_error_message(self):
    tool = AsyncSmoothTool(
      signature=_make_signature(), fn=AsyncMock(), essential=False, error_message="Custom error occurred"
    )
    mock_task = AsyncMock()
    mock_task._send_event = AsyncMock()

    await tool._handle_tool_response(mock_task, "e-1", RuntimeError("internal detail"))

    event = mock_task._send_event.call_args[0][0]
    assert event.payload["output"] == "Custom error occurred"

  async def test_call_full_flow(self):
    """Test the full __call__ flow: calls fn, sends response."""

    async def my_fn(x=1):
      return f"result={x}"

    tool = AsyncSmoothTool(signature=_make_signature(), fn=my_fn, essential=True)

    # Create a mock AsyncTaskHandle
    mock_task = MagicMock()
    mock_task._tools = {}
    mock_task._client = AsyncMock()
    mock_task._client._send_task_event = AsyncMock(return_value=MagicMock(id="resp-1"))
    mock_task._id = "t-1"
    mock_task._event_futures = {}
    mock_task._tool_tasks = {}

    await tool(mock_task, "e-1", x=42)

    # Verify _send_task_event was called (through the AsyncTaskHandleEx wrapper)
    mock_task._client._send_task_event.assert_called_once()


class TestSmoothTool:
  async def test_run_fn_uses_to_thread(self):
    def sync_fn(x=1):
      return f"sync result={x}"

    tool = SmoothTool(signature=_make_signature(), fn=sync_fn, essential=True)
    mock_task = MagicMock()
    result = await tool._run_fn(mock_task, x=5)
    assert result == "sync result=5"

  async def test_run_fn_passes_task_when_named(self):
    def sync_fn(task, x=1):
      return f"has task, x={x}"

    tool = SmoothTool(signature=_make_signature(), fn=sync_fn, essential=True)
    mock_task = MagicMock()
    result = await tool._run_fn(mock_task, x=10)
    assert "has task" in result
    assert "x=10" in result
