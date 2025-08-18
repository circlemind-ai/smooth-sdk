"""Smooth python SDK."""

import asyncio
import logging
import os
import time
from typing import Any, Dict, Literal, Optional, TypeVar, Union

import httpx
import requests
from pydantic import BaseModel, ConfigDict, Field

# Configure logging
logger = logging.getLogger("smooth")


BASE_URL = "https://api2.circlemind.co/api/"

# --- Models ---
# These models define the data structures for API requests and responses.


class TaskData(BaseModel):
  """Task data model."""

  result: Any | None = Field(default=None, description="The result of the task if successful.")
  error: str | None = Field(default=None, description="Error message if the task failed.")
  credits_used: int | None = Field(default=None, description="The amount of credits used to perform the task.")
  src: str | None = Field(default=None, description="")


class TaskResponse(BaseModel):
  """Task response model."""

  model_config = ConfigDict(extra="forbid")

  id: str = Field(description="The ID of the task.")
  status: str = Field(default="RUNNING", description="The status of the task.")
  data: TaskData = Field(default_factory=lambda: TaskData(), description="The data associated with the task.")


class TaskRequest(BaseModel):
  """Run task request model."""

  model_config = ConfigDict(extra="forbid")

  task: str = Field(description="The task to run.")
  agent: Literal["smooth"] = Field(default="smooth", description="The agent to use for the task.")
  max_steps: int = Field(default=32, ge=1, le=64, description="Maximum number of steps the agent can take (max 64).")
  device: Literal["desktop", "mobile"] = Field(default="mobile", description="Device type for the task. Default is mobile.")
  session_id: Optional[str] = Field(
    default=None,
    description="(optional) Browser session ID to use. Each session maintains its own state, such as login credentials.",
  )
  stealth_mode: bool = Field(default=False, description="(optional) Run the browser in stealth mode.")
  proxy_server: Optional[str] = Field(default=None, description="(optional) Proxy server URL.")
  proxy_username: Optional[str] = Field(default=None, description="(optional) Proxy server username.")
  proxy_password: Optional[str] = Field(default=None, description="(optional) Proxy server password.")


class BrowserResponse(BaseModel):
  """Browser session response model."""

  model_config = ConfigDict(extra="forbid")

  live_url: str = Field(description="The live URL to interact with the browser session.")
  session_id: str = Field(description="The ID of the browser session associated with the opened browser instance.")


class BrowserSessionsResponse(BaseModel):
  """Response model for listing browser sessions."""

  session_ids: list[str] = Field(description="The IDs of the browser sessions.")
  session_names: list[str | None] = Field(
    description="The names of the browser sessions (only useful to uniquely identify them)."
  )


T = TypeVar("T")


# --- Exception Handling ---


class ApiError(Exception):
  """Custom exception for API errors."""

  def __init__(self, status_code: int, detail: str, response_data: Optional[Dict[str, Any]] = None):
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

  def __init__(self, api_key: Optional[str] = None, base_url: str = BASE_URL, api_version: str = "v1"):
    """Initializes the base client."""
    # Try to get API key from environment if not provided
    if not api_key:
      api_key = os.getenv("SMOOTH_API_KEY")

    if not api_key:
      raise ValueError("API key is required. Provide it directly or set SMOOTH_API_KEY environment variable.")

    if not base_url:
      raise ValueError("Base URL cannot be empty.")

    self.api_key = api_key
    self.base_url = f"{base_url.rstrip('/')}/{api_version}"
    self.headers = {
      "Authorization": f"Bearer {self.api_key}",
      "Content-Type": "application/json",
      "User-Agent": "smooth-python-sdk/0.1.0",
    }

  def _handle_response(self, response: Union[requests.Response, httpx.Response]) -> dict:
    """Handles HTTP responses and raises exceptions for errors."""
    if 200 <= response.status_code < 300:
      try:
        return response.json()
      except ValueError as e:
        logger.error(f"Failed to parse JSON response: {e}")
        raise ApiError(status_code=response.status_code, detail="Invalid JSON response from server") from None

    # Handle error responses
    try:
      error_data = response.json()
      detail = error_data.get("detail", response.text)
    except ValueError:
      detail = response.text or f"HTTP {response.status_code} error"

    logger.error(f"API error: {response.status_code} - {detail}")
    raise ApiError(
      status_code=response.status_code, detail=detail, response_data=error_data if "error_data" in locals() else None
    )


# --- Synchronous Client ---


class SyncClient(BaseClient):
  """A synchronous client for the API."""

  def __init__(self, api_key: Optional[str] = None, base_url: str = BASE_URL, api_version: str = "v1"):
    """Initializes the synchronous client."""
    super().__init__(api_key, base_url, api_version)
    self._session = requests.Session()
    self._session.headers.update(self.headers)

  def __enter__(self):
    """Enters the synchronous context manager."""
    return self

  def __exit__(self, exc_type, exc_val, exc_tb):
    """Exits the synchronous context manager."""
    self.close()

  def close(self):
    """Close the session."""
    if hasattr(self, "_session"):
      self._session.close()

  def run_task(self, payload: TaskRequest) -> TaskResponse:
    """Submits a task to be run.

    Args:
        payload: The request object containing task details.

    Returns:
        The initial response for the submitted task.

    Raises:
        ApiException: If the API request fails.
    """
    try:
      response = self._session.post(f"{self.base_url}/task", json=payload.model_dump(exclude_none=True))
      data = self._handle_response(response)
      return TaskResponse(**data["r"])
    except requests.exceptions.RequestException as e:
      logger.error(f"Request failed: {e}")
      raise ApiError(status_code=0, detail=f"Request failed: {str(e)}") from None

  def get_task(self, task_id: str) -> TaskResponse:
    """Retrieves the status and result of a task.

    Args:
        task_id: The ID of the task to retrieve.

    Returns:
        The current status and data of the task.

    Raises:
        ApiException: If the API request fails.
        ValueError: If task_id is empty.
    """
    if not task_id:
      raise ValueError("Task ID cannot be empty.")

    try:
      response = self._session.get(f"{self.base_url}/task/{task_id}")
      data = self._handle_response(response)
      return TaskResponse(**data["r"])
    except requests.exceptions.RequestException as e:
      logger.error(f"Request failed: {e}")
      raise ApiError(status_code=0, detail=f"Request failed: {str(e)}") from None

  def run_and_wait_for_task(self, payload: TaskRequest, poll_interval: int = 1, timeout: int = 60 * 15) -> TaskResponse:
    """Runs a task and waits for it to complete.

    This method submits a task and then polls the get_task endpoint
    until the task's status is no longer 'running' or 'waiting'.

    Args:
        payload: The request object containing task details.
        poll_interval: The time in seconds to wait between polling for status.
        timeout: The maximum time in seconds to wait for the task to complete.
        progress_callback: Optional callback function called with TaskResponse on each poll.

    Returns:
        The final response of the completed or failed task.

    Raises:
        TimeoutError: If the task does not complete within the specified timeout.
        ApiException: If the API request fails.
    """
    if poll_interval < 0.1:
      raise ValueError("Poll interval must be at least 100 milliseconds.")
    if timeout < 1:
      raise ValueError("Timeout must be at least 1 second.")

    start_time = time.time()
    initial_response = self.run_task(payload)
    task_id = initial_response.id

    while (time.time() - start_time) < timeout:
      task_response = self.get_task(task_id)

      if task_response.status not in ["running", "waiting"]:
        return task_response

      time.sleep(poll_interval)

    raise TimeoutError(f"Task {task_id} did not complete within {timeout} seconds.")

  def get_browser(self, session_id: Optional[str] = None, session_name: Optional[str] = None) -> BrowserResponse:
    """Gets an interactive browser instance.

    Args:
        session_id: The session ID to associate with the browser. If None, a new session will be created.
        session_name: The name to associate to the new browser session. Ignored if a valid session_id is provided.

    Returns:
        The browser session details, including the live URL.

    Raises:
        ApiException: If the API request fails.
    """
    params = {}
    if session_id:
      params["session_id"] = session_id
    if session_name:
      params["session_name"] = session_name

    try:
      response = self._session.get(f"{self.base_url}/browser", params=params)
      data = self._handle_response(response)
      return BrowserResponse(**data["r"])
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


# --- Asynchronous Client ---


class AsyncClient(BaseClient):
  """An asynchronous client for the API."""

  def __init__(self, api_key: Optional[str] = None, base_url: str = BASE_URL, api_version: str = "v1", timeout: int = 30):
    """Initializes the asynchronous client."""
    super().__init__(api_key, base_url, api_version)
    self._client = httpx.AsyncClient(headers=self.headers, timeout=timeout)

  async def __aenter__(self):
    """Enters the asynchronous context manager."""
    return self

  async def __aexit__(self, exc_type, exc_val, exc_tb):
    """Exits the asynchronous context manager."""
    await self.close()

  async def run_task(self, payload: TaskRequest) -> TaskResponse:
    """Submits a task to be run asynchronously.

    Args:
        payload: The request object containing task details.

    Returns:
        The initial response for the submitted task.

    Raises:
        ApiException: If the API request fails.
    """
    try:
      response = await self._client.post(f"{self.base_url}/task", json=payload.model_dump(exclude_none=True))
      data = self._handle_response(response)
      return TaskResponse(**data["r"])
    except httpx.RequestError as e:
      logger.error(f"Request failed: {e}")
      raise ApiError(status_code=0, detail=f"Request failed: {str(e)}") from None

  async def get_task(self, task_id: str) -> TaskResponse:
    """Retrieves the status and result of a task asynchronously.

    Args:
        task_id: The ID of the task to retrieve.

    Returns:
        The current status and data of the task.

    Raises:
        ApiException: If the API request fails.
        ValueError: If task_id is empty.
    """
    if not task_id:
      raise ValueError("Task ID cannot be empty.")

    try:
      response = await self._client.get(f"{self.base_url}/task/{task_id}")
      data = self._handle_response(response)
      return TaskResponse(**data["r"])
    except httpx.RequestError as e:
      logger.error(f"Request failed: {e}")
      raise ApiError(status_code=0, detail=f"Request failed: {str(e)}") from None

  async def run_and_wait_for_task(self, payload: TaskRequest, poll_interval: int = 1, timeout: int = 60 * 15) -> TaskResponse:
    """Runs a task and waits for it to complete asynchronously.

    This method submits a task and then polls the get_task endpoint
    until the task's status is no longer 'RUNNING' or 'waiting'.

    Args:
        payload: The request object containing task details.
        poll_interval: The time in seconds to wait between polling for status.
        timeout: The maximum time in seconds to wait for the task to complete.
        progress_callback: Optional async callback function called with TaskResponse on each poll.

    Returns:
        The final response of the completed or failed task.

    Raises:
        TimeoutError: If the task does not complete within the specified timeout.
        ApiException: If the API request fails.
    """
    if poll_interval < 0.1:
      raise ValueError("Poll interval must be at least 100 milliseconds.")
    if timeout < 1:
      raise ValueError("Timeout must be at least 1 second.")

    start_time = time.time()
    initial_response = await self.run_task(payload)
    task_id = initial_response.id

    logger.info(f"Task {task_id} started, polling every {poll_interval}s for up to {timeout}s")

    while (time.time() - start_time) < timeout:
      task_status = await self.get_task(task_id)

      if task_status.status.lower() not in ["running", "waiting"]:
        logger.info(f"Task {task_id} completed with status: {task_status.status}")
        return task_status

      await asyncio.sleep(poll_interval)

    raise TimeoutError(f"Task {task_id} did not complete within {timeout} seconds.")

  async def get_browser(self, session_id: Optional[str] = None, session_name: Optional[str] = None) -> BrowserResponse:
    """Gets an interactive browser instance asynchronously.

    Args:
        session_id: The session ID to associate with the browser.
        session_name: The name for a new browser session.

    Returns:
        The browser session details, including the live URL.

    Raises:
        ApiException: If the API request fails.
    """
    params = {}
    if session_id:
      params["session_id"] = session_id
    if session_name:
      params["session_name"] = session_name

    try:
      response = await self._client.get(f"{self.base_url}/browser", params=params)
      data = self._handle_response(response)
      return BrowserResponse(**data["r"])
    except httpx.RequestError as e:
      logger.error(f"Request failed: {e}")
      raise ApiError(status_code=0, detail=f"Request failed: {str(e)}") from None

  async def close(self):
    """Closes the async client session."""
    await self._client.aclose()
