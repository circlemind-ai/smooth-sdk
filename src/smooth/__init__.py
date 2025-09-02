"""Smooth python SDK."""

import asyncio
import logging
import os
import time
import urllib.parse
from typing import Any, Literal, Type

import httpx
import requests
from pydantic import BaseModel, Field

# Configure logging
logger = logging.getLogger("smooth")


BASE_URL = "https://api2.circlemind.co/api/"


# --- Utils ---


def _encode_url(url: str, interactive: bool = True, embed: bool = False) -> str:
  parsed_url = urllib.parse.urlparse(url)
  params = urllib.parse.parse_qs(parsed_url.query)
  params.update({"interactive": "true" if interactive else "false", "embed": "true" if embed else "false"})
  return urllib.parse.urlunparse(parsed_url._replace(query=urllib.parse.urlencode(params)))


# --- Models ---
# These models define the data structures for API requests and responses.


class TaskResponse(BaseModel):
  """Task response model."""

  id: str = Field(description="The ID of the task.")
  status: Literal["waiting", "running", "done", "failed"] = Field(description="The status of the task.")
  output: Any | None = Field(default=None, description="The output of the task.")
  credits_used: int | None = Field(default=None, description="The amount of credits used to perform the task.")
  device: Literal["desktop", "mobile"] | None = Field(default=None, description="The device type used for the task.")
  live_url: str | None = Field(default=None, description="The URL to view and interact with the task execution.")
  recording_url: str | None = Field(default=None, description="The URL to view the task recording.")


class TaskRequest(BaseModel):
  """Run task request model."""

  task: str = Field(description="The task to run.")
  response_model: dict[str, Any] | None = Field(
    default=None, description="If provided, the schema describing the desired output structure. Default is None"
  )
  agent: Literal["smooth"] = Field(default="smooth", description="The agent to use for the task.")
  max_steps: int = Field(default=32, ge=2, le=128, description="Maximum number of steps the agent can take (min 2, max 128).")
  device: Literal["desktop", "mobile"] = Field(default="mobile", description="Device type for the task. Default is mobile.")
  enable_recording: bool = Field(default=True, description="Enable video recording of the task execution. Default is True")
  session_id: str | None = Field(
    default=None,
    description="Browser session ID to use. Each session maintains its own state, such as login credentials.",
  )
  stealth_mode: bool = Field(default=False, description="Run the browser in stealth mode.")
  proxy_server: str | None = Field(
    default=None,
    description=(
      "Proxy server url to route browser traffic through. Must include the protocol to use (e.g. http:// or https://)"
    ),
  )
  proxy_username: str | None = Field(default=None, description="Proxy server username.")
  proxy_password: str | None = Field(default=None, description="Proxy server password.")


class BrowserSessionRequest(BaseModel):
  """Request model for creating a browser session."""

  session_id: str | None = Field(
    default=None,
    description=("The session ID to open in the browser. If None, a new session will be created with a random name."),
  )
  live_view: bool | None = Field(default=True, description="Request a live URL to interact with the browser session.")


class BrowserSessionResponse(BaseModel):
  """Browser session response model."""

  session_id: str = Field(description="The ID of the browser session associated with the opened browser instance.")
  live_url: str | None = Field(default=None, description="The live URL to interact with the browser session.")


class BrowserSessionsResponse(BaseModel):
  """Response model for listing browser sessions."""

  session_ids: list[str] = Field(description="The IDs of the browser sessions.")


# --- Exception Handling ---


class ApiError(Exception):
  """Custom exception for API errors."""

  def __init__(self, status_code: int, detail: str, response_data: dict[str, Any] | None = None):
    """Initializes the API error."""
    self.status_code = status_code
    self.detail = detail
    self.response_data = response_data
    super().__init__(f"API Error {status_code}: {detail}")


class TimeoutError(Exception):
  """Custom exception for task timeouts."""

  pass


# --- Base Client ---


class BaseClient:
  """Base client for handling common API interactions."""

  def __init__(self, api_key: str | None = None, base_url: str = BASE_URL, api_version: str = "v1"):
    """Initializes the base client."""
    # Try to get API key from environment if not provided
    if not api_key:
      api_key = os.getenv("CIRCLEMIND_API_KEY")

    if not api_key:
      raise ValueError("API key is required. Provide it directly or set CIRCLEMIND_API_KEY environment variable.")

    if not base_url:
      raise ValueError("Base URL cannot be empty.")

    self.api_key = api_key
    self.base_url = f"{base_url.rstrip('/')}/{api_version}"
    self.headers = {
      "apikey": self.api_key,
      "Content-Type": "application/json",
      "User-Agent": "smooth-python-sdk/0.1.1",
    }

  def _handle_response(self, response: requests.Response | httpx.Response) -> dict[str, Any]:
    """Handles HTTP responses and raises exceptions for errors."""
    if 200 <= response.status_code < 300:
      try:
        return response.json()
      except ValueError as e:
        logger.error(f"Failed to parse JSON response: {e}")
        raise ApiError(status_code=response.status_code, detail="Invalid JSON response from server") from None

    # Handle error responses
    error_data = None
    try:
      error_data = response.json()
      detail = error_data.get("detail", response.text)
    except ValueError:
      detail = response.text or f"HTTP {response.status_code} error"

    logger.error(f"API error: {response.status_code} - {detail}")
    raise ApiError(status_code=response.status_code, detail=detail, response_data=error_data)


# --- Synchronous Client ---


class BrowserSessionHandle(BaseModel):
  """Browser session handle model."""

  browser_session: BrowserSessionResponse = Field(description="The browser session associated with this handle.")

  def session_id(self):
    """Returns the session ID for the browser session."""
    return self.browser_session.session_id

  def live_url(self, interactive: bool = True, embed: bool = False):
    """Returns the live URL for the browser session."""
    if self.browser_session.live_url:
      return _encode_url(self.browser_session.live_url, interactive=interactive, embed=embed)
    return None


class TaskHandle:
  """A handle to a running task."""

  def __init__(self, task_id: str, client: "SmoothClient"):
    """Initializes the task handle."""
    self._client = client
    self._task_response: TaskResponse | None = None

    self.id = task_id

  def result(self, timeout: int | None = None, poll_interval: float = 1) -> TaskResponse:
    """Waits for the task to complete and returns the result."""
    if self._task_response and self._task_response.status not in ["running", "waiting"]:
      return self._task_response

    if timeout is not None and timeout < 1:
      raise ValueError("Timeout must be at least 1 second.")
    if poll_interval < 0.1:
      raise ValueError("Poll interval must be at least 100 milliseconds.")

    start_time = time.time()
    while timeout is None or (time.time() - start_time) < timeout:
      task_response = self._client._get_task(self.id)  # pyright: ignore [reportPrivateUsage]
      self._task_response = task_response
      if task_response.status not in ["running", "waiting"]:
        return task_response
      time.sleep(poll_interval)
    raise TimeoutError(f"Task {self.id} did not complete within {timeout} seconds.")

  def live_url(self, interactive: bool = True, embed: bool = False, timeout: int | None = None):
    """Returns the live URL for the task."""
    if self._task_response and self._task_response.live_url:
      return _encode_url(self._task_response.live_url, interactive=interactive, embed=embed)

    start_time = time.time()
    while timeout is None or (time.time() - start_time) < timeout:
      task_response = self._client._get_task(self.id)  # pyright: ignore [reportPrivateUsage]
      self._task_response = task_response
      if self._task_response.live_url:
        return _encode_url(self._task_response.live_url, interactive=interactive, embed=embed)
      time.sleep(1)

    raise TimeoutError(f"Live URL not available for task {self.id}.")

  def recording_url(self, timeout: int | None = None) -> str:
    """Returns the recording URL for the task."""
    if self._task_response and self._task_response.recording_url is not None:
      return self._task_response.recording_url

    start_time = time.time()
    while timeout is None or (time.time() - start_time) < timeout:
      task_response = self._client._get_task(self.id)  # pyright: ignore [reportPrivateUsage]
      self._task_response = task_response
      if task_response.recording_url is not None:
        return task_response.recording_url
      time.sleep(1)
    raise TimeoutError(f"Recording URL not available for task {self.id}.")


class SmoothClient(BaseClient):
  """A synchronous client for the API."""

  def __init__(self, api_key: str | None = None, base_url: str = BASE_URL, api_version: str = "v1"):
    """Initializes the synchronous client."""
    super().__init__(api_key, base_url, api_version)
    self._session = requests.Session()
    self._session.headers.update(self.headers)

  def __enter__(self):
    """Enters the synchronous context manager."""
    return self

  def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any):
    """Exits the synchronous context manager."""
    self.close()

  def close(self):
    """Close the session."""
    if hasattr(self, "_session"):
      self._session.close()

  def _submit_task(self, payload: TaskRequest) -> TaskResponse:
    """Submits a task to be run."""
    try:
      response = self._session.post(f"{self.base_url}/task", json=payload.model_dump(exclude_none=True))
      data = self._handle_response(response)
      return TaskResponse(**data["r"])
    except requests.exceptions.RequestException as e:
      logger.error(f"Request failed: {e}")
      raise ApiError(status_code=0, detail=f"Request failed: {str(e)}") from None

  def _get_task(self, task_id: str) -> TaskResponse:
    """Retrieves the status and result of a task."""
    if not task_id:
      raise ValueError("Task ID cannot be empty.")

    try:
      response = self._session.get(f"{self.base_url}/task/{task_id}")
      data = self._handle_response(response)
      return TaskResponse(**data["r"])
    except requests.exceptions.RequestException as e:
      logger.error(f"Request failed: {e}")
      raise ApiError(status_code=0, detail=f"Request failed: {str(e)}") from None

  def run(
    self,
    task: str,
    response_model: dict[str, Any] | Type[BaseModel] | None = None,
    agent: Literal["smooth"] = "smooth",
    max_steps: int = 32,
    device: Literal["desktop", "mobile"] = "mobile",
    enable_recording: bool = False,
    session_id: str | None = None,
    stealth_mode: bool = False,
    proxy_server: str | None = None,
    proxy_username: str | None = None,
    proxy_password: str | None = None,
  ) -> TaskHandle:
    """Runs a task and returns a handle to the task.

    This method submits a task and returns a `TaskHandle` object
    that can be used to get the result of the task.

    Args:
        task: The task to run.
        response_model: If provided, the schema describing the desired output structure.
        agent: The agent to use for the task.
        max_steps: Maximum number of steps the agent can take (max 64).
        device: Device type for the task. Default is mobile.
        enable_recording: Enable video recording of the task execution.
        session_id: Browser session ID to use.
        stealth_mode: Run the browser in stealth mode.
        proxy_server: Proxy server url to route browser traffic through.
        proxy_username: Proxy server username.
        proxy_password: Proxy server password.

    Returns:
        A handle to the running task.

    Raises:
        ApiException: If the API request fails.
    """
    payload = TaskRequest(
      task=task,
      response_model=response_model.model_json_schema() if issubclass(response_model, BaseModel) else response_model,
      agent=agent,
      max_steps=max_steps,
      device=device,
      enable_recording=enable_recording,
      session_id=session_id,
      stealth_mode=stealth_mode,
      proxy_server=proxy_server,
      proxy_username=proxy_username,
      proxy_password=proxy_password,
    )
    initial_response = self._submit_task(payload)

    return TaskHandle(initial_response.id, self)

  def open_session(self, session_id: str | None = None, live_view: bool = True) -> BrowserSessionHandle:
    """Gets an interactive browser instance.

    Args:
        session_id: The session ID to associate with the browser. If None, a new session will be created.
        live_view: Whether to enable live view for the session.

    Returns:
        The browser session details, including the live URL.

    Raises:
        ApiException: If the API request fails.
    """
    try:
      response = self._session.post(
        f"{self.base_url}/browser/session",
        json=BrowserSessionRequest(session_id=session_id, live_view=live_view).model_dump(exclude_none=True),
      )
      data = self._handle_response(response)
      return BrowserSessionHandle(browser_session=BrowserSessionResponse(**data["r"]))
    except requests.exceptions.RequestException as e:
      logger.error(f"Request failed: {e}")
      raise ApiError(status_code=0, detail=f"Request failed: {str(e)}") from None

  def list_sessions(self) -> BrowserSessionsResponse:
    """Lists all browser sessions for the user.

    Returns:
        A list of existing browser sessions.

    Raises:
        ApiException: If the API request fails.
    """
    try:
      response = self._session.get(f"{self.base_url}/browser/session")
      data = self._handle_response(response)
      return BrowserSessionsResponse(**data["r"])
    except requests.exceptions.RequestException as e:
      logger.error(f"Request failed: {e}")
      raise ApiError(status_code=0, detail=f"Request failed: {str(e)}") from None

  def delete_session(self, session_id: str):
    """Delete a browser session."""
    try:
      response = self._session.delete(f"{self.base_url}/browser/session/{session_id}")
      self._handle_response(response)
    except httpx.RequestError as e:
      logger.error(f"Request failed: {e}")
      raise ApiError(status_code=0, detail=f"Request failed: {str(e)}") from None


# --- Asynchronous Client ---


class AsyncTaskHandle:
  """An asynchronous handle to a running task."""

  def __init__(self, task_id: str, client: "SmoothAsyncClient"):
    """Initializes the asynchronous task handle."""
    self._client = client
    self._task_response: TaskResponse | None = None

    self.id = task_id

  async def result(self, timeout: int | None = None, poll_interval: float = 1) -> TaskResponse:
    """Waits for the task to complete and returns the result."""
    if self._task_response and self._task_response.status not in ["running", "waiting"]:
      return self._task_response

    if timeout is not None and timeout < 1:
      raise ValueError("Timeout must be at least 1 second.")
    if poll_interval < 0.1:
      raise ValueError("Poll interval must be at least 100 milliseconds.")

    start_time = time.time()
    while timeout is None or (time.time() - start_time) < timeout:
      task_response = await self._client._get_task(self.id)  # pyright: ignore [reportPrivateUsage]
      self._task_response = task_response
      if task_response.status not in ["running", "waiting"]:
        return task_response
      await asyncio.sleep(poll_interval)
    raise TimeoutError(f"Task {self.id} did not complete within {timeout} seconds.")

  async def live_url(self, interactive: bool = True, embed: bool = False, timeout: int | None = None):
    """Returns the live URL for the task."""
    if self._task_response and self._task_response.live_url:
      return _encode_url(self._task_response.live_url, interactive=interactive, embed=embed)

    start_time = time.time()
    while timeout is None or (time.time() - start_time) < timeout:
      task_response = await self._client._get_task(self.id)  # pyright: ignore [reportPrivateUsage]
      self._task_response = task_response
      if task_response.live_url is not None:
        return _encode_url(self._task_response.live_url, interactive=interactive, embed=embed)
      await asyncio.sleep(1)

    raise TimeoutError(f"Live URL not available for task {self.id}.")

  async def recording_url(self, timeout: int | None = None):
    """Returns the recording URL for the task."""
    if self._task_response and self._task_response.recording_url is not None:
      return self._task_response.recording_url

    start_time = time.time()
    while timeout is None or (time.time() - start_time) < timeout:
      task_response = await self._client._get_task(self.id)  # pyright: ignore [reportPrivateUsage]
      self._task_response = task_response
      if task_response.recording_url is not None:
        return task_response.recording_url
      await asyncio.sleep(1)

    raise TimeoutError(f"Recording URL not available for task {self.id}.")


class SmoothAsyncClient(BaseClient):
  """An asynchronous client for the API."""

  def __init__(self, api_key: str | None = None, base_url: str = BASE_URL, api_version: str = "v1", timeout: int = 30):
    """Initializes the asynchronous client."""
    super().__init__(api_key, base_url, api_version)
    self._client = httpx.AsyncClient(headers=self.headers, timeout=timeout)

  async def __aenter__(self):
    """Enters the asynchronous context manager."""
    return self

  async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any):
    """Exits the asynchronous context manager."""
    await self.close()

  async def _submit_task(self, payload: TaskRequest) -> TaskResponse:
    """Submits a task to be run asynchronously."""
    try:
      response = await self._client.post(f"{self.base_url}/task", json=payload.model_dump(exclude_none=True))
      data = self._handle_response(response)
      return TaskResponse(**data["r"])
    except httpx.RequestError as e:
      logger.error(f"Request failed: {e}")
      raise ApiError(status_code=0, detail=f"Request failed: {str(e)}") from None

  async def _get_task(self, task_id: str) -> TaskResponse:
    """Retrieves the status and result of a task asynchronously."""
    if not task_id:
      raise ValueError("Task ID cannot be empty.")

    try:
      response = await self._client.get(f"{self.base_url}/task/{task_id}")
      data = self._handle_response(response)
      return TaskResponse(**data["r"])
    except httpx.RequestError as e:
      logger.error(f"Request failed: {e}")
      raise ApiError(status_code=0, detail=f"Request failed: {str(e)}") from None

  async def run(
    self,
    task: str,
    response_model: dict[str, Any] | Type[BaseModel] | None = None,
    agent: Literal["smooth"] = "smooth",
    max_steps: int = 32,
    device: Literal["desktop", "mobile"] = "mobile",
    enable_recording: bool = False,
    session_id: str | None = None,
    stealth_mode: bool = False,
    proxy_server: str | None = None,
    proxy_username: str | None = None,
    proxy_password: str | None = None,
  ) -> AsyncTaskHandle:
    """Runs a task and returns a handle to the task asynchronously.

    This method submits a task and returns an `AsyncTaskHandle` object
    that can be used to get the result of the task.

    Args:
        task: The task to run.
        response_model: If provided, the schema describing the desired output structure.
        agent: The agent to use for the task.
        max_steps: Maximum number of steps the agent can take (max 64).
        device: Device type for the task. Default is mobile.
        enable_recording: Enable video recording of the task execution.
        session_id: Browser session ID to use.
        stealth_mode: Run the browser in stealth mode.
        proxy_server: Proxy server url to route browser traffic through.
        proxy_username: Proxy server username.
        proxy_password: Proxy server password.
        poll_interval: The time in seconds to wait between polling for status.
        timeout: The maximum time in seconds to wait for the task to complete.

    Returns:
        A handle to the running task.

    Raises:
        ApiException: If the API request fails.
    """
    payload = TaskRequest(
      task=task,
      response_model=response_model.model_json_schema() if issubclass(response_model, BaseModel) else response_model,
      agent=agent,
      max_steps=max_steps,
      device=device,
      enable_recording=enable_recording,
      session_id=session_id,
      stealth_mode=stealth_mode,
      proxy_server=proxy_server,
      proxy_username=proxy_username,
      proxy_password=proxy_password,
    )

    initial_response = await self._submit_task(payload)
    return AsyncTaskHandle(initial_response.id, self)

  async def open_session(self, session_id: str | None = None, live_view: bool = True) -> BrowserSessionHandle:
    """Opens an interactive browser instance asynchronously.

    Args:
        session_id: The session ID to associate with the browser.
        live_view: Whether to enable live view for the session.

    Returns:
        The browser session details, including the live URL.

    Raises:
        ApiException: If the API request fails.
    """
    try:
      response = await self._client.post(
        f"{self.base_url}/browser/session",
        json=BrowserSessionRequest(session_id=session_id, live_view=live_view).model_dump(exclude_none=True),
      )
      data = self._handle_response(response)
      return BrowserSessionHandle(browser_session=BrowserSessionResponse(**data["r"]))
    except httpx.RequestError as e:
      logger.error(f"Request failed: {e}")
      raise ApiError(status_code=0, detail=f"Request failed: {str(e)}") from None

  async def list_sessions(self) -> BrowserSessionsResponse:
    """Lists all browser sessions for the user.

    Returns:
        A list of existing browser sessions.

    Raises:
        ApiException: If the API request fails.
    """
    try:
      response = await self._client.get(f"{self.base_url}/browser/session")
      data = self._handle_response(response)
      return BrowserSessionsResponse(**data["r"])
    except httpx.RequestError as e:
      logger.error(f"Request failed: {e}")
      raise ApiError(status_code=0, detail=f"Request failed: {str(e)}") from None

  async def delete_session(self, session_id: str):
    """Delete a browser session."""
    try:
      response = await self._client.delete(f"{self.base_url}/browser/session/{session_id}")
      self._handle_response(response)
    except httpx.RequestError as e:
      logger.error(f"Request failed: {e}")
      raise ApiError(status_code=0, detail=f"Request failed: {str(e)}") from None

  async def close(self):
    """Closes the async client session."""
    await self._client.aclose()


# Export public API
__all__ = [
  "SmoothClient",
  "SmoothAsyncClient",
  "TaskHandle",
  "AsyncTaskHandle",
  "BrowserSessionHandle",
  "TaskRequest",
  "TaskResponse",
  "BrowserSessionRequest",
  "BrowserSessionResponse",
  "BrowserSessionsResponse",
  "ApiError",
  "TimeoutError",
]
