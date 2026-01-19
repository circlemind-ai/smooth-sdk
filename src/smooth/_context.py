import asyncio
import os
import time
from typing import Any, Callable, cast

import httpx

from smooth._utils import encode_url

from ._base import BASE_URL, ApiError, ContextRequest, ContextResponse, TaskEvent, TaskRequest, TaskResponse, logger


class BaseClient:
  """Base client for handling API interactions."""

  def __init__(
    self,
    client: httpx.Client,
    api_key: str | None = None,
    base_url: str = BASE_URL,
    api_version: str = "v2",
  ):
    """Initializes the base client."""
    # Try to get API key from environment if not provided
    if not api_key:
      api_key = os.getenv("CIRCLEMIND_API_KEY")

    if not api_key:
      raise ValueError("API key is required. Provide it directly or set CIRCLEMIND_API_KEY environment variable.")

    if not base_url:
      raise ValueError("Base URL cannot be empty.")

    self.client = client
    client.base_url = f"{base_url.rstrip('/')}/{api_version}"
    client.headers = {
      "apikey": api_key,
      "User-Agent": "smooth-python-sdk/1.0.0",
    }

  def _handle_response(self, response: httpx.Response) -> dict[str, Any] | Any:
    """Handles HTTP responses and raises exceptions for errors."""
    if 200 <= response.status_code < 300:
      try:
        return response.json()
      except ValueError as e:
        logger.error(f"Failed to parse JSON response: {e}")
        raise ApiError(
          status_code=response.status_code,
          detail="Invalid JSON response from server",
        ) from None

    # Handle error responses
    error_data = None
    try:
      error_data = response.json()
      detail = error_data.get("detail", response.text)
    except ValueError:
      detail = response.text or f"HTTP {response.status_code} error"

    logger.error(f"API error: {response.status_code} - {detail}")
    raise ApiError(status_code=response.status_code, detail=detail, response_data=error_data)

  def create_context(self, payload: ContextRequest) -> str:
    return cast(str, self._handle_response(self.client.post("ctx", json=payload.model_dump())))

  def get_context(self, ctx_id: str, query_params: dict[str, Any] | None = None) -> ContextResponse:
    return ContextResponse(**self._handle_response(self.client.get(f"ctx/{ctx_id}", params=query_params)))

  def delete_context(self, ctx_id: str) -> None:
    self._handle_response(self.client.delete(f"ctx/{ctx_id}"))

  def create_task(self, ctx_id: str, payload: TaskRequest) -> str:
    return cast(str, self._handle_response(self.client.post(f"ctx/{ctx_id}/task", json=payload.model_dump())))

  def get_task(self, task_id: str, query_params: dict[str, Any] | None = None) -> TaskResponse:
    return TaskResponse(**self._handle_response(self.client.get(f"task/{task_id}", params=query_params)))

  # def _send_task_event(self, task_id: str, event: TaskEvent) -> TaskEventResponse:
  #   raise NotImplementedError


class AsyncBaseClient(BaseClient):
  """Async Base client for handling API interactions."""

  def __init__(
    self,
    client: httpx.AsyncClient,
    api_key: str | None = None,
    base_url: str = BASE_URL,
    api_version: str = "v1",
  ):
    """Initializes the base client."""
    # Try to get API key from environment if not provided
    if not api_key:
      api_key = os.getenv("CIRCLEMIND_API_KEY")

    if not api_key:
      raise ValueError("API key is required. Provide it directly or set CIRCLEMIND_API_KEY environment variable.")

    if not base_url:
      raise ValueError("Base URL cannot be empty.")

    self.client = client
    client.base_url = f"{base_url.rstrip('/')}/{api_version}"
    client.headers = {
      "apikey": api_key,
      "User-Agent": "smooth-python-sdk/1.0.0",
    }

  async def create_context(self, payload: ContextRequest) -> str:
    return cast(str, self._handle_response(await self.client.post("ctx", json=payload.model_dump())))

  async def get_context(self, ctx_id: str, query_params: dict[str, Any] | None = None) -> ContextResponse:
    return ContextResponse(**self._handle_response(await self.client.get(f"ctx/{ctx_id}", params=query_params)))

  async def delete_context(self, ctx_id: str) -> None:
    self._handle_response(await self.client.delete(f"ctx/{ctx_id}"))

  async def create_task(self, ctx_id: str, payload: TaskRequest) -> str:
    return cast(str, self._handle_response(await self.client.post(f"ctx/{ctx_id}/task", json=payload.model_dump())))

  async def get_task(self, task_id: str, query_params: dict[str, Any] | None = None) -> TaskResponse:
    return TaskResponse(**self._handle_response(await self.client.get(f"task/{task_id}", params=query_params)))

  # def _send_task_event(self, task_id: str, event: TaskEvent) -> TaskEventResponse:
  #   raise NotImplementedError


class TaskHandle:
  """A handle to a running task."""

  def __init__(self, task_id: str, client: BaseClient):
    """Initializes the task handle."""
    self._id = task_id
    self._client = client
    self._task_response: TaskResponse | None = None

  def id(self):
    """Returns the task ID."""
    return self._id

  def send_event(self, event: TaskEvent) -> Any | None:
    raise NotImplementedError

  def result(self, timeout: int | None = None, poll_interval: float = 1) -> TaskResponse:
    raise NotImplementedError


class AsyncTaskHandle:
  """A handle to a running async task."""

  def __init__(self, task_id: str, client: AsyncBaseClient):
    """Initializes the async task handle."""
    self._id = task_id
    self._client = client
    self._task_response: TaskResponse | None = None

  def id(self):
    """Returns the task ID."""
    return self._id

  async def send_event(self, event: TaskEvent) -> Any | None:
    raise NotImplementedError

  async def result(self, timeout: int | None = None, poll_interval: float = 1) -> TaskResponse:
    raise NotImplementedError


class ContextHandle:
  """Base context class."""

  _ctx_id: str
  _ctx: ContextResponse | None

  def __init__(self, ctx_id: str, client: BaseClient):
    self._client = client
    self._ctx_id = ctx_id
    self._ctx = None

  def __enter__(self) -> "ContextHandle":
    return self

  def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
    pass

  def id(self) -> str:
    """Returns the context ID."""
    return self._ctx_id

  def run_task(self, payload: Any):
    return TaskHandle(self._client.create_task(self._ctx_id, payload), self._client)

  def live_url(self, interactive: bool, embed: bool = False, timeout: int | None = None) -> str:
    if self._ctx and self._ctx.live_url:
      url = self._ctx.live_url
    else:
      url = self._fetch_context_data(lambda ctx: ctx and ctx.live_url, {}, timeout=timeout)

    return encode_url(url, interactive=interactive, embed=embed)

  def recording_url(self, timeout: int | None = None):
    return self._fetch_context_data(
      lambda ctx: ctx and ctx.recording_url,
      {},
      timeout=timeout,
      raise_if_none=(
        f"Recording URL not available for context {self.id()}."
        " Set `enable_recording=True` when creating the context to enable it."
      ),
    )

  def downloads_url(self, timeout: int | None = None):
    return self._fetch_context_data(
      lambda ctx: ctx and ctx.downloads_url,
      {},
      timeout=timeout,
      raise_if_none=f"No downloaded files found for context {self.id()}.",
    )

  def close(self) -> None:
    """Deletes the context."""
    self._client.delete_context(self._ctx_id)

  def _fetch_context_data(
    self,
    fn: Callable[[ContextResponse | None], str | None],
    params: dict[str, Any],
    timeout: int | None = None,
    raise_if_none: str | None = None,
  ):
    data = fn(self._ctx)
    if data is None:
      start_time = time.time()
      while True:
        self._ctx = self._client.get_context(self._ctx_id, query_params=params)
        result = fn(self._ctx)
        if result is not None:
          data = result
          break

        if timeout is None or (time.time() - start_time) < timeout:
          raise ApiError(
            status_code=408,
            detail=f"Timeout while waiting for context {self.id()} data.",
          )
        else:
          time.sleep(1)

    if not data and raise_if_none:
      raise ApiError(
        status_code=404,
        detail=raise_if_none,
      )
    return data


class AsyncContextHandle(ContextHandle):
  """Base async context class."""

  def __init__(self, ctx_id: str, client: AsyncBaseClient):
    self._client = client
    self._ctx_id = ctx_id
    self._ctx = None

  async def __aenter__(self) -> "AsyncContextHandle":
    return self

  async def __aexit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
    pass

  async def run_task(self, payload: Any):
    return AsyncTaskHandle(await self._client.create_task(self._ctx_id, payload), self._client)

  async def live_url(self, interactive: bool, embed: bool = False, timeout: int | None = None) -> str:
    if self._ctx and self._ctx.live_url:
      url = self._ctx.live_url
    else:
      url = await self._fetch_context_data(
        lambda ctx: ctx and ctx.live_url, {}, timeout=timeout, raise_if_none=f"Live URL not available for context {self.id()}"
      )
    return encode_url(url, interactive=interactive, embed=embed)

  async def recording_url(self, timeout: int | None = None):
    return await self._fetch_context_data(
      lambda ctx: ctx and ctx.recording_url,
      {},
      timeout=timeout,
      raise_if_none=(
        f"Recording URL not available for context {self.id()}."
        " Set `enable_recording=True` when creating the context to enable it."
      ),
    )

  async def downloads_url(self, timeout: int | None = None):
    return await self._fetch_context_data(
      lambda ctx: ctx and ctx.downloads_url,
      {},
      timeout=timeout,
      raise_if_none=f"No downloaded files found for context {self.id()}.",
    )

  async def _fetch_context_data(
    self,
    fn: Callable[[ContextResponse | None], str | None],
    params: dict[str, Any],
    timeout: int | None = None,
    raise_if_none: str | None = None,
  ):
    loop = asyncio.get_event_loop()
    data = fn(self._ctx)
    if data is None:
      start_time = loop.time()
      while True:
        self._ctx = await self._client.get_context(self._ctx_id, query_params=params)
        result = fn(self._ctx)
        if result is not None:
          data = result
          break

        if timeout is None or (loop.time() - start_time) < timeout:
          raise ApiError(
            status_code=408,
            detail=f"Timeout while waiting for context {self.id()} data.",
          )
        else:
          await asyncio.sleep(1)

    if not data and raise_if_none:
      raise ApiError(
        status_code=404,
        detail=raise_if_none,
      )
    return data
