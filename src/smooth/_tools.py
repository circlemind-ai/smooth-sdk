# pyright: reportPrivateUsage=false
import asyncio
import inspect
from typing import TYPE_CHECKING, Any, Callable

from ._exceptions import ToolCallError
from .models import TaskEvent, ToolSignature

if TYPE_CHECKING:
  from ._interface import AsyncTaskHandle


class AsyncSmoothTool:
  def __init__(
    self,
    signature: ToolSignature,
    fn: Callable[..., Any],
    essential: bool,
    error_message: str | None = None,
  ) -> None:
    self.signature = signature
    self._essential = essential
    self._error_message = error_message

    # If fn is sync (not a coroutine function), wrap it to run in executor
    if not inspect.iscoroutinefunction(fn):

      async def async_wrapper(task: Any = None, **kwargs: Any) -> Any:
        sig = inspect.signature(fn)
        params = list(sig.parameters.values())
        loop = asyncio.get_event_loop()
        if params and params[0].name == "task":
          return await loop.run_in_executor(None, lambda: fn(task, **kwargs))
        else:
          return await loop.run_in_executor(None, lambda: fn(**kwargs))

      self._fn = async_wrapper
    else:
      # Already async, use as-is
      self._fn = fn

  @property
  def name(self) -> str:
    return self.signature.name

  async def __call__(self, task: "AsyncTaskHandle", event_id: str | None, **kwargs: Any) -> Any:
    try:
      # Detect if first element of _fn is called `task` and pass task if so
      sig = inspect.signature(self._fn)
      params = list(sig.parameters.values())

      # Call the function (now always async)
      if params and params[0].name == "task":
        response = await self._fn(task, **kwargs)
      else:
        response = await self._fn(**kwargs)
      await task.send_event(
        TaskEvent(
          id=event_id,
          name="tool_call",
          payload={
            "code": 200,
            "output": response,
          },
        )
      )
    except ToolCallError as e:
      await task.send_event(
        TaskEvent(
          id=event_id,
          name="tool_call",
          payload={
            "code": 400,
            "output": str(e),
          },
        )
      )
    except Exception as e:
      await task.send_event(
        TaskEvent(
          id=event_id,
          name="tool_call",
          payload={
            "code": 500 if self._essential else 400,
            "output": self._error_message or str(e),
          },
        )
      )
      if self._essential:
        raise e


# SmoothTool is just an alias for AsyncSmoothTool since it now handles sync functions automatically
SmoothTool = AsyncSmoothTool
