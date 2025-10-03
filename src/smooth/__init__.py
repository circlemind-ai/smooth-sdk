"""Smooth python SDK."""

import asyncio
import io
import logging
import os
import time
import urllib.parse
import warnings
from pathlib import Path
from typing import Any, Literal, Type

import httpx
import requests
from deprecated import deprecated
from pydantic import BaseModel, Field, model_validator

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
    default=None, description="If provided, the JSON schema describing the desired output structure. Default is None"
  )
  url: str | None = Field(
    default=None,
    description="The starting URL for the task. If not provided, the agent will infer it from the task.",
  )
  metadata: dict[str, str | int | float | bool] | None = Field(
    default=None, description="A dictionary containing variables or parameters that will be passed to the agent."
  )
  files: list[str] | None = Field(default=None, description="A list of file ids to pass to the agent.")
  agent: Literal["smooth"] = Field(default="smooth", description="The agent to use for the task.")
  max_steps: int = Field(default=32, ge=2, le=128, description="Maximum number of steps the agent can take (min 2, max 128).")
  device: Literal["desktop", "mobile"] = Field(default="mobile", description="Device type for the task. Default is mobile.")
  allowed_urls: list[str] | None = Field(
    default=None,
    description=(
      "List of allowed URL patterns using wildcard syntax (e.g., https://*example.com/*). If None, all URLs are allowed."
    ),
  )
  enable_recording: bool = Field(default=True, description="Enable video recording of the task execution. Default is True")
  profile_id: str | None = Field(
    default=None,
    description=("Browser profile ID to use. Each profile maintains its own state, such as cookies and login credentials."),
  )
  profile_read_only: bool = Field(
    default=False, description="If true, the profile specified by `profile_id` will be loaded in read-only mode."
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
  experimental_features: dict[str, Any] | None = Field(default=None, description="Experimental features to enable for the task.")

  @model_validator(mode="before")
  @classmethod
  def _handle_deprecated_session_id(cls, data: Any) -> Any:
    if isinstance(data, dict) and "session_id" in data:
      warnings.warn("'session_id' is deprecated, use 'profile_id' instead", DeprecationWarning, stacklevel=2)
      data["profile_id"] = data.pop("session_id")
    return data

  @property
  def session_id(self):
    """(Deprecated) Returns the session ID."""
    warnings.warn("'session_id' is deprecated, use 'profile_id' instead", DeprecationWarning, stacklevel=2)
    return self.profile_id

  @session_id.setter
  def session_id(self, value):
    """(Deprecated) Sets the session ID."""
    warnings.warn("'session_id' is deprecated, use 'profile_id' instead", DeprecationWarning, stacklevel=2)
    self.profile_id = value


class BrowserSessionRequest(BaseModel):
  """Request model for creating a browser session."""

  profile_id: str | None = Field(
    default=None, description=("The profile ID to use for the browser session. If None, a new profile will be created.")
  )
  live_view: bool | None = Field(default=True, description="Request a live URL to interact with the browser session.")

  @model_validator(mode="before")
  @classmethod
  def _handle_deprecated_session_id(cls, data: Any) -> Any:
    if isinstance(data, dict) and "session_id" in data:
      warnings.warn("'session_id' is deprecated, use 'profile_id' instead", DeprecationWarning, stacklevel=2)
      data["profile_id"] = data.pop("session_id")
    return data

  @property
  def session_id(self):
    """(Deprecated) Returns the session ID."""
    warnings.warn("'session_id' is deprecated, use 'profile_id' instead", DeprecationWarning, stacklevel=2)
    return self.profile_id

  @session_id.setter
  def session_id(self, value):
    """(Deprecated) Sets the session ID."""
    warnings.warn("'session_id' is deprecated, use 'profile_id' instead", DeprecationWarning, stacklevel=2)
    self.profile_id = value


class BrowserSessionResponse(BaseModel):
  """Browser session response model."""

  profile_id: str = Field(description="The ID of the browser profile associated with the opened browser instance.")
  live_url: str | None = Field(default=None, description="The live URL to interact with the browser session.")

  @model_validator(mode="before")
  @classmethod
  def _handle_deprecated_session_id(cls, data: Any) -> Any:
    if isinstance(data, dict) and "session_id" in data:
      warnings.warn("'session_id' is deprecated, use 'profile_id' instead", DeprecationWarning, stacklevel=2)
      data["profile_id"] = data.pop("session_id")
    return data

  @property
  def session_id(self):
    """(Deprecated) Returns the session ID."""
    warnings.warn("'session_id' is deprecated, use 'profile_id' instead", DeprecationWarning, stacklevel=2)
    return self.profile_id

  @session_id.setter
  def session_id(self, value):
    """(Deprecated) Sets the session ID."""
    warnings.warn("'session_id' is deprecated, use 'profile_id' instead", DeprecationWarning, stacklevel=2)
    self.profile_id = value


class BrowserProfilesResponse(BaseModel):
  """Response model for listing browser profiles."""

  profile_ids: list[str] = Field(description="The IDs of the browser profiles.")

  @model_validator(mode="before")
  @classmethod
  def _handle_deprecated_session_ids(cls, data: Any) -> Any:
    if isinstance(data, dict) and "session_ids" in data:
      warnings.warn("'session_ids' is deprecated, use 'profile_ids' instead", DeprecationWarning, stacklevel=2)
      data["profile_ids"] = data.pop("session_ids")
    return data

  @property
  def session_ids(self):
    """(Deprecated) Returns the session IDs."""
    warnings.warn("'session_ids' is deprecated, use 'profile_ids' instead", DeprecationWarning, stacklevel=2)
    return self.profile_ids

  @session_ids.setter
  def session_ids(self, value):
    """(Deprecated) Sets the session IDs."""
    warnings.warn("'session_ids' is deprecated, use 'profile_ids' instead", DeprecationWarning, stacklevel=2)
    self.profile_ids = value


class BrowserSessionsResponse(BrowserProfilesResponse):
  """Response model for listing browser profiles."""
  pass


class UploadFileResponse(BaseModel):
  """Response model for uploading a file."""

  id: str = Field(description="The ID assigned to the uploaded file.")


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
      "User-Agent": "smooth-python-sdk/0.2.5",
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
      return _encode_url(self.browser_session.live_url, interactive=interactive, embed=embed)
    return None


class TaskHandle:
  """A handle to a running task."""

  def __init__(self, task_id: str, client: "SmoothClient"):
    """Initializes the task handle."""
    self._client = client
    self._task_response: TaskResponse | None = None

    self._id = task_id

  def id(self):
    """Returns the task ID."""
    return self._id

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
      task_response = self._client._get_task(self.id())
      self._task_response = task_response
      if task_response.status not in ["running", "waiting"]:
        return task_response
      time.sleep(poll_interval)
    raise TimeoutError(f"Task {self.id()} did not complete within {timeout} seconds.")

  def live_url(self, interactive: bool = True, embed: bool = False, timeout: int | None = None):
    """Returns the live URL for the task."""
    if self._task_response and self._task_response.live_url:
      return _encode_url(self._task_response.live_url, interactive=interactive, embed=embed)

    start_time = time.time()
    while timeout is None or (time.time() - start_time) < timeout:
      task_response = self._client._get_task(self.id())
      self._task_response = task_response
      if self._task_response.live_url:
        return _encode_url(self._task_response.live_url, interactive=interactive, embed=embed)
      time.sleep(1)

    raise TimeoutError(f"Live URL not available for task {self.id()}.")

  def recording_url(self, timeout: int | None = None) -> str:
    """Returns the recording URL for the task."""
    if self._task_response and self._task_response.recording_url is not None:
      return self._task_response.recording_url

    start_time = time.time()
    while timeout is None or (time.time() - start_time) < timeout:
      task_response = self._client._get_task(self.id())
      self._task_response = task_response
      if task_response.recording_url is not None:
        return task_response.recording_url
      time.sleep(1)
    raise TimeoutError(f"Recording URL not available for task {self.id()}.")


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
    url: str | None = None,
    metadata: dict[str, str | int | float | bool] | None = None,
    files: list[str] | None = None,
    agent: Literal["smooth"] = "smooth",
    max_steps: int = 32,
    device: Literal["desktop", "mobile"] = "mobile",
    allowed_urls: list[str] | None = None,
    enable_recording: bool = False,
    session_id: str | None = None,
    profile_id: str | None = None,
    profile_read_only: bool | None = None,
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
        url: The starting URL for the task. If not provided, the agent will infer it from the task.
        metadata: A dictionary containing variables or parameters that will be passed to the agent.
        files: A dictionary of file names to their ids. These files will be passed to the agent.
        agent: The agent to use for the task.
        max_steps: Maximum number of steps the agent can take (max 64).
        device: Device type for the task. Default is mobile.
        allowed_urls: List of allowed URL patterns using wildcard syntax (e.g., https://*example.com/*).
          If None, all URLs are allowed.
        enable_recording: Enable video recording of the task execution.
        session_id: (Deprecated, now `profile_id`) Browser session ID to use.
        profile_id: Browser profile ID to use. Each profile maintains its own state, such as cookies and login credentials.
        profile_read_only: If true, the profile specified by `profile_id` will be loaded in read-only mode.
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
      url=url,
      metadata=metadata,
      files=files,
      agent=agent,
      max_steps=max_steps,
      device=device,
      allowed_urls=allowed_urls,
      enable_recording=enable_recording,
      profile_id=profile_id or session_id,
      profile_read_only=profile_read_only,
      stealth_mode=stealth_mode,
      proxy_server=proxy_server,
      proxy_username=proxy_username,
      proxy_password=proxy_password,
    )
    initial_response = self._submit_task(payload)

    return TaskHandle(initial_response.id, self)

  def open_session(
    self, profile_id: str | None = None, session_id: str | None = None, live_view: bool = True
  ) -> BrowserSessionHandle:
    """Opens an interactive browser instance to interact with a specific browser profile.

    Args:
        profile_id: The profile ID to use for the session. If None, a new profile will be created.
        session_id: (Deprecated, now `profile_id`) The session ID to associate with the browser.
        live_view: Whether to enable live view for the session.

    Returns:
        The browser session details, including the live URL.

    Raises:
        ApiException: If the API request fails.
    """
    try:
      response = self._session.post(
        f"{self.base_url}/browser/session",
        json=BrowserSessionRequest(profile_id=profile_id or session_id, live_view=live_view).model_dump(exclude_none=True),
      )
      data = self._handle_response(response)
      return BrowserSessionHandle(browser_session=BrowserSessionResponse(**data["r"]))
    except requests.exceptions.RequestException as e:
      logger.error(f"Request failed: {e}")
      raise ApiError(status_code=0, detail=f"Request failed: {str(e)}") from None

  def list_profiles(self):
    """Lists all browser profiles for the user.

    Returns:
        A list of existing browser profiles.

    Raises:
        ApiException: If the API request fails.
    """
    try:
      response = self._session.get(f"{self.base_url}/browser/session")
      data = self._handle_response(response)
      return BrowserProfilesResponse(**data["r"])
    except requests.exceptions.RequestException as e:
      logger.error(f"Request failed: {e}")
      raise ApiError(status_code=0, detail=f"Request failed: {str(e)}") from None

  @deprecated("list_sessions is deprecated, use list_profiles instead")
  def list_sessions(self):
    """Lists all browser profiles for the user."""
    return self.list_profiles()

  def delete_profile(self, profile_id: str):
    """Delete a browser profile."""
    try:
      response = self._session.delete(f"{self.base_url}/browser/session/{profile_id}")
      self._handle_response(response)
    except requests.exceptions.RequestException as e:
      logger.error(f"Request failed: {e}")
      raise ApiError(status_code=0, detail=f"Request failed: {str(e)}") from None

  @deprecated("delete_session is deprecated, use delete_profile instead")
  def delete_session(self, session_id: str):
    """Delete a browser profile."""
    self.delete_profile(session_id)

  def upload_file(self, file: io.IOBase, name: str | None = None, purpose: str | None = None) -> UploadFileResponse:
    """Upload a file and return the file ID.

    Args:
        file: File object to be uploaded.
        name: Optional custom name for the file. If not provided, the original file name will be used.
        purpose: Optional short description of the file to describe its purpose (i.e., 'the bank statement pdf').

    Returns:
        The file ID assigned to the uploaded file.

    Raises:
        ValueError: If the file doesn't exist or can't be read.
        ApiError: If the API request fails.
    """
    try:
      name = name or getattr(file, "name", None)
      if name is None:
        raise ValueError("File name must be provided or the file object must have a 'name' attribute.")

      if purpose:
        data = {"file_purpose": purpose}
      else:
        data = None

      files = {"file": (Path(name).name, file)}
      response = self._session.post(f"{self.base_url}/file", files=files, data=data)
      data = self._handle_response(response)
      return UploadFileResponse(**data["r"])
    except requests.exceptions.RequestException as e:
      logger.error(f"Request failed: {e}")
      raise ApiError(status_code=0, detail=f"Request failed: {str(e)}") from None

  def delete_file(self, file_id: str):
    """Delete a file by its ID."""
    try:
      response = self._session.delete(f"{self.base_url}/file/{file_id}")
      self._handle_response(response)
    except requests.exceptions.RequestException as e:
      logger.error(f"Request failed: {e}")
      raise ApiError(status_code=0, detail=f"Request failed: {str(e)}") from None


# --- Asynchronous Client ---


class AsyncTaskHandle:
  """An asynchronous handle to a running task."""

  def __init__(self, task_id: str, client: "SmoothAsyncClient"):
    """Initializes the asynchronous task handle."""
    self._client = client
    self._task_response: TaskResponse | None = None

    self._id = task_id

  def id(self):
    """Returns the task ID."""
    return self._id

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
      task_response = await self._client._get_task(self.id())
      self._task_response = task_response
      if task_response.status not in ["running", "waiting"]:
        return task_response
      await asyncio.sleep(poll_interval)
    raise TimeoutError(f"Task {self.id()} did not complete within {timeout} seconds.")

  async def live_url(self, interactive: bool = True, embed: bool = False, timeout: int | None = None):
    """Returns the live URL for the task."""
    if self._task_response and self._task_response.live_url:
      return _encode_url(self._task_response.live_url, interactive=interactive, embed=embed)

    start_time = time.time()
    while timeout is None or (time.time() - start_time) < timeout:
      task_response = await self._client._get_task(self.id())
      self._task_response = task_response
      if task_response.live_url is not None:
        return _encode_url(self._task_response.live_url, interactive=interactive, embed=embed)
      await asyncio.sleep(1)

    raise TimeoutError(f"Live URL not available for task {self.id()}.")

  async def recording_url(self, timeout: int | None = None):
    """Returns the recording URL for the task."""
    if self._task_response and self._task_response.recording_url is not None:
      return self._task_response.recording_url

    start_time = time.time()
    while timeout is None or (time.time() - start_time) < timeout:
      task_response = await self._client._get_task(self.id())
      self._task_response = task_response
      if task_response.recording_url is not None:
        return task_response.recording_url
      await asyncio.sleep(1)

    raise TimeoutError(f"Recording URL not available for task {self.id()}.")


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
    url: str | None = None,
    metadata: dict[str, str | int | float | bool] | None = None,
    files: list[str] | None = None,
    agent: Literal["smooth"] = "smooth",
    max_steps: int = 32,
    device: Literal["desktop", "mobile"] = "mobile",
    allowed_urls: list[str] | None = None,
    enable_recording: bool = False,
    session_id: str | None = None,
    profile_id: str | None = None,
    profile_read_only: bool | None = None,
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
        url: The starting URL for the task. If not provided, the agent will infer it from the task.
        metadata: A dictionary containing variables or parameters that will be passed to the agent.
        files: A dictionary of file names to their url or base64-encoded content to be used by the agent.
        agent: The agent to use for the task.
        max_steps: Maximum number of steps the agent can take (max 64).
        device: Device type for the task. Default is mobile.
        allowed_urls: List of allowed URL patterns using wildcard syntax (e.g., https://*example.com/*).
          If None, all URLs are allowed.
        enable_recording: Enable video recording of the task execution.
        session_id: (Deprecated, now `profile_id`) Browser session ID to use.
        profile_id: Browser profile ID to use. Each profile maintains its own state, such as cookies and login credentials.
        profile_read_only: If true, the profile specified by `profile_id` will be loaded in read-only mode.
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
      url=url,
      metadata=metadata,
      files=files,
      agent=agent,
      max_steps=max_steps,
      device=device,
      allowed_urls=allowed_urls,
      enable_recording=enable_recording,
      profile_id=profile_id or session_id,
      profile_read_only=profile_read_only,
      stealth_mode=stealth_mode,
      proxy_server=proxy_server,
      proxy_username=proxy_username,
      proxy_password=proxy_password,
    )

    initial_response = await self._submit_task(payload)
    return AsyncTaskHandle(initial_response.id, self)

  async def open_session(
    self, profile_id: str | None = None, session_id: str | None = None, live_view: bool = True
  ) -> BrowserSessionHandle:
    """Opens an interactive browser instance asynchronously.

    Args:
        session_id: (Deprecated, now `profile_id`) The session ID to associate with the browser.
        profile_id: The profile ID to associate with the browser.
        live_view: Whether to enable live view for the session.

    Returns:
        The browser session details, including the live URL.

    Raises:
        ApiException: If the API request fails.
    """
    try:
      response = await self._client.post(
        f"{self.base_url}/browser/session",
        json=BrowserSessionRequest(profile_id=profile_id or session_id, live_view=live_view).model_dump(exclude_none=True),
      )
      data = self._handle_response(response)
      return BrowserSessionHandle(browser_session=BrowserSessionResponse(**data["r"]))
    except httpx.RequestError as e:
      logger.error(f"Request failed: {e}")
      raise ApiError(status_code=0, detail=f"Request failed: {str(e)}") from None

  async def list_profiles(self):
    """Lists all browser profiles for the user.

    Returns:
        A list of existing browser profiles.

    Raises:
        ApiException: If the API request fails.
    """
    try:
      response = await self._client.get(f"{self.base_url}/browser/session")
      data = self._handle_response(response)
      return BrowserProfilesResponse(**data["r"])
    except httpx.RequestError as e:
      logger.error(f"Request failed: {e}")
      raise ApiError(status_code=0, detail=f"Request failed: {str(e)}") from None

  @deprecated("list_sessions is deprecated, use list_profiles instead")
  async def list_sessions(self):
    """Lists all browser profiles for the user."""
    return await self.list_profiles()

  async def delete_profile(self, profile_id: str):
    """Delete a browser profile."""
    try:
      response = await self._client.delete(f"{self.base_url}/browser/session/{profile_id}")
      self._handle_response(response)
    except httpx.RequestError as e:
      logger.error(f"Request failed: {e}")
      raise ApiError(status_code=0, detail=f"Request failed: {str(e)}") from None

  @deprecated("delete_session is deprecated, use delete_profile instead")
  async def delete_session(self, session_id: str):
    """Delete a browser profile."""
    await self.delete_profile(session_id)

  async def upload_file(self, file: io.IOBase, name: str | None = None, purpose: str | None = None) -> UploadFileResponse:
    """Upload a file and return the file ID.

    Args:
        file: File object to be uploaded.
        name: Optional custom name for the file. If not provided, the original file name will be used.
        purpose: Optional short description of the file to describe its purpose (i.e., 'the bank statement pdf').

    Returns:
        The file ID assigned to the uploaded file.

    Raises:
        ValueError: If the file doesn't exist or can't be read.
        ApiError: If the API request fails.
    """
    try:
      name = name or getattr(file, "name", None)
      if name is None:
        raise ValueError("File name must be provided or the file object must have a 'name' attribute.")

      files = {"file": (Path(name).name, file)}
      if purpose:
        data = {"file_purpose": purpose}
      else:
        data = None
      response = await self._client.post(f"{self.base_url}/file", files=files, data=data)
      data = self._handle_response(response)
      return UploadFileResponse(**data["r"])
    except httpx.RequestError as e:
      logger.error(f"Request failed: {e}")
      raise ApiError(status_code=0, detail=f"Request failed: {str(e)}") from None

  async def delete_file(self, file_id: str):
    """Delete a file by its ID."""
    try:
      response = await self._client.delete(f"{self.base_url}/file/{file_id}")
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
  "UploadFileResponse",
  "ApiError",
  "TimeoutError",
]
