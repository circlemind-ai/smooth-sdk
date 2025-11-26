import inspect
from typing import Any, Callable

from ._base import BaseAsyncTaskHandle, BaseTaskHandle, TaskEvent, ToolCallError, ToolSignature


class SmoothTool:
  def __init__(
    self,
    signature: ToolSignature,
    fn: Callable[..., Any],
    essential: bool,
    error_message: str | None = None,
  ) -> None:
    self.signature = signature
    self._fn = fn
    self._essential = essential
    self._error_message = error_message

  @property
  def name(self) -> str:
    return self.signature.name

  def __call__(self, task: BaseTaskHandle, event_id: str | None, **kwargs: Any) -> Any:
    try:
      sig = inspect.signature(self._fn)
      params = list(sig.parameters.values())
      if params and params[0].name == "task":
        response = self._fn(task, **kwargs)
      else:
        response = self._fn(**kwargs)
      task.send_event(
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
      task.send_event(
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
      task.send_event(
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


class AsyncSmoothTool:
  def __init__(
    self,
    signature: ToolSignature,
    fn: Callable[..., Any],
    essential: bool,
    error_message: str | None = None,
  ) -> None:
    self.signature = signature
    self._fn = fn
    self._essential = essential
    self._error_message = error_message

  @property
  def name(self) -> str:
    return self.signature.name

  async def __call__(self, task: BaseAsyncTaskHandle, event_id: str | None, **kwargs: Any) -> Any:
    try:
      # Detect if first element of _fn is called `task` and pass task if so
      sig = inspect.signature(self._fn)
      params = list(sig.parameters.values())
      if params and params[0].name == "task":
        response = self._fn(task, **kwargs)
      else:
        response = self._fn(**kwargs)
      if inspect.isawaitable(response):
        response = await response
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
