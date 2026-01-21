# pyright: reportPrivateUsage=false
import asyncio
import inspect
from typing import TYPE_CHECKING, Any, Callable, Coroutine

from ._exceptions import ToolCallError
from .models import TaskEvent, ToolSignature

if TYPE_CHECKING:
  from ._interface import AsyncTaskHandle, TaskHandle


class AsyncSmoothTool:
  def __init__(
    self,
    signature: ToolSignature,
    fn: Callable[..., Coroutine[Any, Any, Any]],
    essential: bool,
    error_message: str | None = None,
  ) -> None:
    self.signature = signature
    self._essential = essential
    self._error_message = error_message
    self._fn = fn

  @property
  def name(self) -> str:
    return self.signature.name

  async def _run_fn(self, task: "AsyncTaskHandle", **kwargs: Any) -> Any:
    # Detect if first element of _fn is called `task` and pass task if so
    params = list(inspect.signature(self._fn).parameters.values())

    if params and params[0].name == "task":
      return await self._fn(task, **kwargs)
    else:
      return await self._fn(**kwargs)

  async def _handle_tool_response(self, task: "AsyncTaskHandle", event_id: str, response: Any) -> Any:
    if isinstance(response, ToolCallError):
      await task._send_event(
        TaskEvent(
          id=event_id,
          name="tool_call",
          payload={
            "code": 400,
            "output": str(response),
          },
        )
      )
    elif isinstance(response, Exception):
      await task._send_event(
        TaskEvent(
          id=event_id,
          name="tool_call",
          payload={
            "code": 500 if self._essential else 400,
            "output": self._error_message or str(response),
          },
        )
      )
      if self._essential:
        raise response
    else:
      await task._send_event(
        TaskEvent(
          id=event_id,
          name="tool_call",
          payload={
            "code": 200,
            "output": response,
          },
        )
      )

  async def __call__(self, task: "AsyncTaskHandle", event_id: str, **kwargs: Any) -> Any:
    try:
      response = await self._run_fn(task, **kwargs)
      await self._handle_tool_response(task, event_id, response)
    except Exception as e:
      await self._handle_tool_response(task, event_id, e)


class SmoothTool(AsyncSmoothTool):
  def __init__(
    self,
    signature: ToolSignature,
    fn: Callable[..., Any],
    essential: bool,
    error_message: str | None = None,
  ) -> None:
    super().__init__(signature, fn, essential, error_message)

  async def _run_fn(self, task: "TaskHandle", **kwargs: Any) -> Any:
    # Detect if first element of _fn is called `task` and pass task if so
    params = list(inspect.signature(self._fn).parameters.values())

    if params and params[0].name == "task":
      return await asyncio.to_thread(self._fn, task, **kwargs)
    else:
      return await asyncio.to_thread(self._fn, **kwargs)

  async def __call__(self, task: "TaskHandle", event_id: str, **kwargs: Any) -> Any:
    try:
      response = await self._run_fn(task, **kwargs)
      await self._handle_tool_response(task._async_handle, event_id, response)
    except Exception as e:
      await self._handle_tool_response(task._async_handle, event_id, e)
