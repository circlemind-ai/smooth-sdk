"""Smooth python SDK."""

import asyncio
import logging
import os
import time
from typing import (
  Any,
  Literal,
)

import httpx
import requests
from pydantic import BaseModel, ConfigDict, Field

# Configure logging
logger = logging.getLogger("smooth")


BASE_URL = "https://api2.circlemind.co/api/"

# --- Models ---
# These models define the data structures for API requests and responses.


class TaskResponse(BaseModel):
  """Task response model."""

  model_config = ConfigDict(extra="forbid")

  id: str = Field(description="The ID of the task.")
  status: Literal["waiting", "running", "done", "failed"] = Field(description="The status of the task.")
  result: Any | None = Field(default=None, description="The result of the task if successful.")
  error: str | None = Field(default=None, description="Error message if the task failed.")
  credits_used: int | None = Field(default=None, description="The amount of credits used to perform the task.")
  src: str | None = Field(default=None, description="")


class TaskRequest(BaseModel):
  """Run task request model."""

  model_config = ConfigDict(extra="forbid")

  task: str = Field(description="The task to run.")
  agent: Literal["smooth"] = Field(default="smooth", description="The agent to use for the task.")
  max_steps: int = Field(default=32, ge=1, le=64, description="Maximum number of steps the agent can take (max 64).")
  device: Literal["desktop", "mobile"] = Field(default="mobile", description="Device type for the task. Default is mobile.")
  enable_recording: bool = Field(default=False, description="(optional) Enable video recording of the task execution.")
  session_id: str | None = Field(
    default=None,
    description="(optional) Browser session ID to use. Each session maintains its own state, such as login credentials.",
  )
  stealth_mode: bool = Field(default=False, description="(optional) Run the browser in stealth mode.")
  proxy_server: str | None = Field(
    default=None,
    description=(
      "(optional) Proxy server url to route browser traffic through."
      " Must include the protocol to use (e.g. http:// or https://)"
    ),
  )
  proxy_username: str | None = Field(default=None, description="(optional) Proxy server username.")
  proxy_password: str | None = Field(default=None, description="(optional) Proxy server password.")


class BrowserSessionRequest(BaseModel):
  """Request model for creating a browser session."""

  session_id: str | None = Field(
    default=None, description="The session ID to associate to the browser instance. If None, a new session will be created."
  )
  session_name: str | None = Field(
    default=None, description="The name to associate to the new browser session. Ignored if a valid session_id is provided."
  )


class BrowserSessionResponse(BaseModel):
  """Browser session response model."""

  model_config = ConfigDict(extra="forbid")

  live_url: str = Field(description="The live URL to interact with the browser session.")
  session_id: str = Field(description="The ID of the browser session associated with the opened browser instance.")


class BrowserSessionsResponse(BaseModel):
  """Response model for listing browser sessions."""

  session_ids: list[str] = Field(description="The IDs of the browser sessions.")
  session_names: list[str | None] = Field(description="The names of the browser sessions.")


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
      "User-Agent": "smooth-python-sdk/0.1.0",
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

  def submit_task(self, payload: TaskRequest) -> TaskResponse:
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

  def run(
    self,
    task: str,
    poll_interval: int = 1,
    timeout: int = 60 * 15,
    agent: Literal["smooth"] = "smooth",
    max_steps: int = 32,
    device: Literal["desktop", "mobile"] = "mobile",
    enable_recording: bool = False,
    session_id: str | None = None,
    stealth_mode: bool = False,
    proxy_server: str | None = None,
    proxy_username: str | None = None,
    proxy_password: str | None = None,
  ) -> TaskResponse:
    """Runs a task and waits for it to complete.

    This method submits a task and then polls the get_task endpoint
    until the task's status is no longer 'running' or 'waiting'.

    Args:
        task: The task to run.
        poll_interval: The time in seconds to wait between polling for status.
        timeout: The maximum time in seconds to wait for the task to complete.
        agent: The agent to use for the task.
        max_steps: Maximum number of steps the agent can take (max 64).
        device: Device type for the task. Default is mobile.
        enable_recording: (optional) Enable video recording of the task execution.
        session_id: (optional) Browser session ID to use.
        stealth_mode: (optional) Run the browser in stealth mode.
        proxy_server: (optional) Proxy server url to route browser traffic through.
        proxy_username: (optional) Proxy server username.
        proxy_password: (optional) Proxy server password.

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

    payload = TaskRequest(
      task=task,
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

    start_time = time.time()
    initial_response = self.submit_task(payload)
    task_id = initial_response.id

    while (time.time() - start_time) < timeout:
      task_response = self.get_task(task_id)

      if task_response.status not in ["running", "waiting"]:
        return task_response

      time.sleep(poll_interval)

    raise TimeoutError(f"Task {task_id} did not complete within {timeout} seconds.")

  def open_session(self, session_id: str | None = None, session_name: str | None = None) -> BrowserSessionResponse:
    """Gets an interactive browser instance.

    Args:
        session_id: The session ID to associate with the browser. If None, a new session will be created.
        session_name: The name to associate to the new browser session. Ignored if a valid session_id is provided.

    Returns:
        The browser session details, including the live URL.

    Raises:
        ApiException: If the API request fails.
    """
    try:
      response = self._session.post(
        f"{self.base_url}/browser/session",
        json=BrowserSessionRequest(session_id=session_id, session_name=session_name).model_dump(exclude_none=True),
      )
      data = self._handle_response(response)
      return BrowserSessionResponse(**data["r"])
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

  async def submit_task(self, payload: TaskRequest) -> TaskResponse:
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

  async def run(
    self,
    task: str,
    poll_interval: int = 1,
    timeout: int = 60 * 15,
    agent: Literal["smooth"] = "smooth",
    max_steps: int = 32,
    device: Literal["desktop", "mobile"] = "mobile",
    enable_recording: bool = False,
    session_id: str | None = None,
    stealth_mode: bool = False,
    proxy_server: str | None = None,
    proxy_username: str | None = None,
    proxy_password: str | None = None,
  ) -> TaskResponse:
    """Runs a task and waits for it to complete asynchronously.

    This method submits a task and then polls the get_task endpoint
    until the task's status is no longer 'running' or 'waiting'.

    Args:
        task: The task to run.
        poll_interval: The time in seconds to wait between polling for status.
        timeout: The maximum time in seconds to wait for the task to complete.
        agent: The agent to use for the task.
        max_steps: Maximum number of steps the agent can take (max 64).
        device: Device type for the task. Default is mobile.
        enable_recording: (optional) Enable video recording of the task execution.
        session_id: (optional) Browser session ID to use.
        stealth_mode: (optional) Run the browser in stealth mode.
        proxy_server: (optional) Proxy server url to route browser traffic through.
        proxy_username: (optional) Proxy server username.
        proxy_password: (optional) Proxy server password.

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

    payload = TaskRequest(
      task=task,
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

    start_time = time.time()
    initial_response = await self.submit_task(payload)
    task_id = initial_response.id

    while (time.time() - start_time) < timeout:
      task_response = await self.get_task(task_id)

      if task_response.status not in ["running", "waiting"]:
        return task_response

      await asyncio.sleep(poll_interval)

    raise TimeoutError(f"Task {task_id} did not complete within {timeout} seconds.")

  async def open_session(self, session_id: str | None = None, session_name: str | None = None) -> BrowserSessionResponse:
    """Opens an interactive browser instance asynchronously.

    Args:
        session_id: The session ID to associate with the browser.
        session_name: The name for a new browser session.

    Returns:
        The browser session details, including the live URL.

    Raises:
        ApiException: If the API request fails.
    """
    try:
      response = await self._client.post(
        f"{self.base_url}/browser/session",
        json=BrowserSessionRequest(session_id=session_id, session_name=session_name).model_dump(exclude_none=True),
      )
      data = self._handle_response(response)
      return BrowserSessionResponse(**data["r"])
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

  async def close(self):
    """Closes the async client session."""
    await self._client.aclose()
