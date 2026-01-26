# pyright: reportPrivateUsage=false
import asyncio
import random
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, Coroutine, Sequence, TypeVar

from deprecated import deprecated
from nanoid import generate
from pydantic import BaseModel, Field

from ._exceptions import ApiError, BadRequestError, ToolCallError
from ._utils import encode_url, logger
from .models import (
  ActionEvaluateJSResponse,
  ActionExtractResponse,
  ActionGotoResponse,
  ActionRunTaskResponse,
  BrowserSessionResponse,
  TaskEvent,
  TaskResponse,
  TaskUpdateRequest,
)

if TYPE_CHECKING:
  from ._client import SmoothAsyncClient, SmoothClient
  from ._tools import AsyncSmoothTool, SmoothTool

T = TypeVar("T")


class BaseTaskHandle:
  """A handle to a running task."""

  def __init__(self, task_id: str):
    """Initializes the task handle."""
    self._id = task_id
    self._task_response = None

  def id(self):
    """Returns the task ID."""
    return self._id


class AsyncTaskHandle(BaseTaskHandle):
  """An asynchronous handle to a running task."""

  def __init__(
    self,
    task_id: str,
    client: "SmoothAsyncClient",
    tools: Sequence["AsyncSmoothTool"] | None = None,
    task_handle: Any | None = None,
  ):
    """Initializes the asynchronous task handle."""
    super().__init__(task_id)
    self._client = client
    self._tools = {tool.name: tool for tool in (tools or [])}
    self._task_handle = task_handle or self  # Use to pass the correct handle to tools
    # Polling
    self._is_alive = 0
    self._poll_interval = 1.0
    self._polling_task: asyncio.Task[Any] | None = None

    # Events
    self._last_event_t = 0
    self._event_futures: dict[str, asyncio.Future[Any]] = {}
    self._tool_tasks: dict[str, asyncio.Task[Any]] = {}

  # --- Task Methods ---

  @deprecated("stop is deprecated")
  async def stop(self):
    """Stops the task."""
    await self._client._delete_task(self._id)

  async def result(self, timeout: int | None = None, poll_interval: float | None = None):
    """Waits for the task to complete and returns the result."""
    if self._task_response and self._task_response.status not in [
      "running",
      "waiting",
    ]:
      return self._task_response

    if timeout is not None and timeout < 1:
      raise ValueError("Timeout must be at least 1 second.")

    if poll_interval is not None:
      logger.warning("poll_interval is deprecated.")

    loop = asyncio.get_running_loop()
    async with self._connection():
      start_time = loop.time()
      while timeout is None or (loop.time() - start_time) < timeout:
        if self._task_response and self._task_response.status not in ["running", "waiting"]:
          return self._task_response

        await asyncio.sleep(0.2)
      raise TimeoutError(f"Task {self.id()} did not complete within {timeout} seconds.")

  async def live_url(self, interactive: bool = False, embed: bool = False, timeout: int | None = None):
    """Returns the live URL for the task."""
    if self._task_response and self._task_response.live_url:
      return encode_url(self._task_response.live_url, interactive=interactive, embed=embed)

    loop = asyncio.get_running_loop()
    async with self._connection():
      start_time = loop.time()
      while timeout is None or (loop.time() - start_time) < timeout:
        if self._task_response and self._task_response.live_url:
          return encode_url(self._task_response.live_url, interactive=interactive, embed=embed)
        await asyncio.sleep(0.2)

    raise TimeoutError(f"Live URL not available for task {self.id()}.")

  async def recording_url(self, timeout: int | None = 30) -> str:
    """Returns the recording URL for the task."""
    if self._task_response and self._task_response.recording_url is not None:
      return self._task_response.recording_url

    loop = asyncio.get_running_loop()
    async with self._connection():
      start_time = loop.time()
      while timeout is None or (loop.time() - start_time) < timeout:
        if self._task_response and self._task_response.recording_url is not None:
          if not self._task_response.recording_url:
            raise ApiError(
              status_code=404,
              detail=(
                f"Recording URL not available for task {self.id()}."
                " Set `enable_recording=True` when creating the task to enable it."
              ),
            )
          return self._task_response.recording_url
        await asyncio.sleep(0.2)

    if self._task_response and self._task_response.status in ["waiting", "running"]:
      raise BadRequestError(f"Recording URL not available for task {self.id()} while it is still running.")
    raise TimeoutError(f"Recording URL not available for task {self.id()}.")

  async def downloads_url(self, timeout: int | None = 30) -> str:
    """Returns the downloads URL for the task."""
    if self._task_response and self._task_response.downloads_url is not None:
      return self._task_response.downloads_url

    loop = asyncio.get_running_loop()
    async with self._connection():
      start_time = loop.time()
      while timeout is None or (loop.time() - start_time) < timeout:
        if self._task_response and self._task_response.status not in ["waiting", "running"]:
          task_response = await self._client._get_task(self.id(), query_params={"downloads": "true"})
          if task_response.downloads_url is not None:
            if not task_response.downloads_url:
              raise ApiError(
                status_code=404,
                detail=(
                  f"Downloads URL not available for task {self.id()}."
                  " Make sure the task downloaded files during its execution."
                ),
              )
            return task_response.downloads_url
          await asyncio.sleep(0.8)
        await asyncio.sleep(0.2)

    if self._task_response and self._task_response.status in ["waiting", "running"]:
      raise BadRequestError(f"Downloads URL not available for task {self.id()} while it is still running.")
    raise TimeoutError(f"Downloads URL not available for task {self.id()}.")

  async def _send_event(self, event: TaskEvent, has_result: bool = False) -> Any | None:
    """Sends an event to a running task."""
    event.id = event.id or generate()
    if has_result:
      future = asyncio.get_running_loop().create_future()
      self._event_futures[event.id] = future

      await self._client._send_task_event(self._id, event)
      async with self._connection():
        return await future
    else:
      await self._client._send_task_event(self._id, event)
      return None

  # --- Action Methods ---

  async def goto(self, url: str):
    """Navigates to the given URL."""
    event = TaskEvent(
      name="browser_action",
      payload={
        "name": "goto",
        "input": {"url": url},
      },
    )
    return ActionGotoResponse(**((await self._send_event(event, has_result=True)) or {}))  # type: ignore

  async def extract(self, schema: dict[str, Any], prompt: str | None = None):
    """Extracts from the given URL."""
    event = TaskEvent(
      name="browser_action",
      payload={
        "name": "extract",
        "input": {
          "schema": schema,
          "prompt": prompt,
        },
      },
    )
    return ActionExtractResponse(**((await self._send_event(event, has_result=True)) or {}))  # type: ignore

  async def evaluate_js(self, code: str, args: dict[str, Any] | None = None):
    """Executes JavaScript code in the browser context."""
    event = TaskEvent(
      name="browser_action",
      payload={
        "name": "evaluate_js",
        "input": {
          "js": code,
          "args": args,
        },
      },
    )
    return ActionEvaluateJSResponse(**((await self._send_event(event, has_result=True)) or {}))  # type: ignore

  # --- Private Methods ---

  async def _connect(self):
    # We use a counter to keep track of how many clients requested a connection
    # so we know to (i) start polling only once, and (ii) stop polling only when all clients have disconnected
    self._is_alive += 1

    if self._is_alive != 1:
      return

    async def _run_tool(fn: Coroutine[Any, Any, Any], event_id: str) -> Any:
      try:
        return await fn
      except asyncio.CancelledError:
        raise
      finally:
        self._tool_tasks.pop(event_id, None)

    self._task_response = await self._client._get_task(self.id(), query_params={"event_t": self._last_event_t})

    async def _poller():
      poller_id = generate()
      logger.debug(f"Starting poller {poller_id} for task {self.id()}")
      try:
        while self._is_alive > 0:
          logger.debug(f"{poller_id} - polling")
          await asyncio.sleep(self._poll_interval)

          task_response = await self._client._get_task(self.id(), query_params={"event_t": self._last_event_t})
          self._task_response = task_response

          if task_response.status not in ["running", "waiting"]:
            raise RuntimeError("Task is not running.")
          elif task_response.events:
            self._last_event_t = task_response.events[-1].timestamp or self._last_event_t
            for event in task_response.events:
              if not event.id:
                continue
              if event.name == "tool_call" and (tool := self._tools.get(event.payload.get("name", ""))) is not None:
                self._tool_tasks[event.id] = asyncio.create_task(
                  _run_tool(tool(self._task_handle, event.id, **event.payload.get("input", {})), event.id)
                )
              elif event.name == "browser_action":
                future = self._event_futures.get(event.id)
                if future and not future.done():
                  self._event_futures.pop(event.id, None)
                  code = event.payload.get("code")
                  if code == 200:
                    future.set_result(event.payload.get("output"))
                  elif code == 400:
                    future.set_exception(ToolCallError(event.payload.get("output", "Unknown error.")))
                  elif code == 500:
                    future.set_exception(RuntimeError(event.payload.get("output", "Unknown error.")))

          for task in self._tool_tasks.values():
            if task.done():
              await task
      except asyncio.CancelledError:
        logger.debug("Poller %s for task %s cancelled", poller_id, self.id())
      finally:
        # Cancel all pending futures
        for future in self._event_futures.values():
          if not future.done():
            future.cancel()
        self._event_futures.clear()

        # Cancel all running tool tasks
        for task in self._tool_tasks.values():
          if not task.done():
            task.cancel()
        self._tool_tasks.clear()
      logger.debug("Poller %s for task %s stopped", poller_id, self.id())

    await asyncio.sleep(random.uniform(0, self._poll_interval))  # Stagger pollers
    self._polling_task = asyncio.create_task(_poller())

  def _disconnect(self):
    """Disconnects the task handle from the task."""
    self._is_alive = 0 if self._is_alive < 1 else self._is_alive - 1
    if self._is_alive == 0 and self._polling_task and not self._polling_task.done():
      self._polling_task.cancel()

  @asynccontextmanager
  async def _connection(self):
    """Context manager to connect to the task."""
    await self._connect()
    try:
      yield self
    finally:
      self._disconnect()

  # --- Deprecated Methods ---

  @deprecated("update is deprecated, use send_event instead")
  async def update(self, payload: TaskUpdateRequest) -> bool:
    """Updates a running task with user input."""
    return await self._client._update_task(self._id, payload)

  @deprecated("exec_js is deprecated, use evaluate_js instead")
  async def exec_js(self, code: str, args: dict[str, Any] | None = None) -> asyncio.Future[Any]:
    """Executes JavaScript code in the browser context."""
    event = TaskEvent(
      name="browser_action",
      payload={
        "name": "exec_js",
        "input": {
          "js": code,
          "args": args,
        },
      },
    )
    # TODO: This is non-blocking for backward compatibility (old _send_event)
    event.id = event.id or generate()
    future = asyncio.get_running_loop().create_future()
    self._event_futures[event.id] = future

    asyncio.create_task(self._client._send_task_event(self._id, event))
    return future


class AsyncSessionHandle(AsyncTaskHandle):
  """A handle to an open browser session."""

  async def __aenter__(self):
    """Enters the context manager."""
    await self._connect()
    return self

  async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any):
    """Exits the context manager."""
    if exc_type is None:
      await self.close(force=False)
    else:
      await self.close(force=True)

  # --- Session Methods ---

  async def close(self, force: bool = True):
    """Closes the session."""
    if not force:
      event = TaskEvent(
        name="browser_action",
        payload={
          "name": "close",
        },
      )
      await self._send_event(event, has_result=False)
    else:
      await self._client._delete_task(self._id)
    self._disconnect()

  async def run_task(
    self,
    task: str,
    max_steps: int = 32,
    response_model: dict[str, Any] | None = None,
    url: str | None = None,
    metadata: dict[str, Any] | None = None,
  ):
    """Extracts from the given URL."""
    event = TaskEvent(
      name="browser_action",
      payload={
        "name": "run_task",
        "input": {
          "task": task,
          "max_steps": max_steps,
          "response_model": response_model,
          "url": url,
          "metadata": metadata,
        },
      },
    )
    return ActionRunTaskResponse(**(await self._send_event(event, has_result=True) or {}))  # type: ignore


class TaskHandle(BaseTaskHandle):
  """A synchronous handle to a running task (wraps AsyncTaskHandle)."""

  def __init__(self, task_id: str, client: "SmoothClient", tools: list["SmoothTool"] | None = None):
    """Initializes the task handle."""
    super().__init__(task_id)
    self._client = client
    self._loop = client._loop  # Use client's event loop

    self._async_handle = AsyncTaskHandle(task_id, client._async_client, tools, self)

  def _run_async(self, coro: Coroutine[Any, Any, T]) -> T:
    return self._client._run_async(coro)

  @deprecated("stop is deprecated")
  def stop(self):
    """Stops the task."""
    self._run_async(self._async_handle.stop())

  def result(self, timeout: int | None = None, poll_interval: float | None = None) -> TaskResponse:
    """Waits for the task to complete and returns the result."""
    return self._run_async(self._async_handle.result(timeout, poll_interval))

  def live_url(self, interactive: bool = False, embed: bool = False, timeout: int | None = None) -> str:
    """Returns the live URL for the task."""
    return self._run_async(self._async_handle.live_url(interactive, embed, timeout))

  def recording_url(self, timeout: int | None = None) -> str:
    """Returns the recording URL for the task."""
    return self._run_async(self._async_handle.recording_url(timeout))

  def downloads_url(self, timeout: int | None = None) -> str:
    """Returns the downloads URL for the task."""
    return self._run_async(self._async_handle.downloads_url(timeout))

  def goto(self, url: str) -> Any:
    """Navigates to the given URL."""
    return self._run_async(self._async_handle.goto(url))

  def extract(self, schema: dict[str, Any], prompt: str | None = None) -> Any:
    """Extracts from the given URL."""
    return self._run_async(self._async_handle.extract(schema, prompt))

  def evaluate_js(self, code: str, args: dict[str, Any] | None = None) -> Any:
    """Evaluates JavaScript code in the browser context."""
    return self._run_async(self._async_handle.evaluate_js(code, args))

  @deprecated("update is deprecated, use send_event instead")
  def update(self, payload: TaskUpdateRequest) -> bool:
    """Updates a running task with user input."""
    return self._run_async(self._async_handle.update(payload))

  @deprecated("exec_js is deprecated, use evaluate_js instead")
  def exec_js(self, code: str, args: dict[str, Any] | None = None) -> Any:
    """Executes JavaScript code in the browser context."""

    # NOTE: this was blocking before, so we keep it that way for backward compatibility
    async def _run() -> Any:
      return await (await self._async_handle.exec_js(code, args))

    return self._run_async(_run())


class SessionHandle(TaskHandle):
  """A handle to an open browser session."""

  def __init__(self, task_id: str, client: "SmoothClient", tools: list["SmoothTool"] | None = None):
    """Initializes the task handle."""
    super().__init__(task_id, client, tools)

    self._async_handle = AsyncSessionHandle(task_id, client._async_client, tools)

  def __enter__(self):
    """Enters the context manager."""
    self._run_async(self._async_handle.__aenter__())
    return self

  def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any):
    """Exits the context manager."""
    self._run_async(self._async_handle.__aexit__(exc_type, exc_val, exc_tb))

  def close(self, force: bool = True):
    """Closes the session."""
    return self._run_async(self._async_handle.close(force))

  def run_task(
    self,
    task: str,
    max_steps: int = 32,
    response_model: dict[str, Any] | None = None,
    url: str | None = None,
    metadata: dict[str, Any] | None = None,
  ):
    """Extracts from the given URL."""
    return self._run_async(self._async_handle.run_task(task, max_steps, response_model, url, metadata))


###############################################################################################################
# --- Deprecated ---
###############################################################################################################


class BrowserSessionHandle(BaseModel):
  """Browser session handle model."""

  browser_session: BrowserSessionResponse = Field(description="The browser session associated with this handle.")

  @deprecated("session_id is deprecated, use profile_id instead")
  def session_id(self):
    """Returns the session ID for the browser session."""
    return self.profile_id()

  def profile_id(self):
    """Returns the profile ID for the browser session."""
    return self.browser_session.profile_id

  def live_url(self, interactive: bool = True, embed: bool = False):
    """Returns the live URL for the browser session."""
    if self.browser_session.live_url:
      return encode_url(self.browser_session.live_url, interactive=interactive, embed=embed)
    return None

  def live_id(self):
    """Returns the live ID for the browser session."""
    return self.browser_session.live_id
