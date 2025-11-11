import inspect
import json
from typing import Any, Callable

from ._base import BaseAsyncTaskHandle, BaseTaskHandle, TaskUpdateRequest, ToolCallError, ToolCallResponse, ToolSignature


class SmoothTool:
  def __init__(
    self,
    signature: ToolSignature,
    fn: Callable[..., Any],
    error_message: str | None = None,
  ) -> None:
    self.signature = signature
    self._fn = fn
    self._error_message = error_message

  @property
  def name(self) -> str:
    return self.signature.name

  def __call__(self, task: BaseTaskHandle, call_id: str, **kwargs: Any) -> Any:
    try:
      response = self._fn(**kwargs)
      response_json = json.dumps(response)
      if len(response_json) > 64_000:
        raise ValueError(self.signature.name, "Tool response too large to send back (max ~64KB).")
      task.update(
        TaskUpdateRequest(
          tool_response=ToolCallResponse(
            id=call_id,
            code=200,
            output=response_json,
          )
        )
      )
    except ToolCallError as e:
      task.update(TaskUpdateRequest(tool_response=ToolCallResponse(id=call_id, code=400, output=str(e))))
    except Exception as e:
      task.update(TaskUpdateRequest(tool_response=ToolCallResponse(id=call_id, code=500, output=self._error_message or "")))
      raise e


class AsyncSmoothTool:
  def __init__(
    self,
    signature: ToolSignature,
    fn: Callable[..., Any],
    error_message: str | None = None,
  ) -> None:
    self.signature = signature
    self._fn = fn
    self._error_message = error_message

  @property
  def name(self) -> str:
    return self.signature.name

  async def __call__(self, task: BaseAsyncTaskHandle, call_id: str, *args: Any, **kwargs: Any) -> Any:
    try:
      response = self._fn(*args, **kwargs)
      if inspect.isawaitable(response):
        response = await response
      response_json = json.dumps(response)
      if len(response_json) > 64_000:
        raise ValueError(self.signature.name, "Tool response too large to send back (max ~64KB).")
      await task.update(
        TaskUpdateRequest(
          tool_response=ToolCallResponse(
            id=call_id,
            code=200,
            output=response_json,
          )
        )
      )
    except ToolCallError as e:
      await task.update(TaskUpdateRequest(tool_response=ToolCallResponse(id=call_id, code=400, output=str(e))))
    except Exception as e:
      await task.update(
        TaskUpdateRequest(tool_response=ToolCallResponse(id=call_id, code=500, output=self._error_message or ""))
      )
      raise e
