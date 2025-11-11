# pyright: reportPrivateUsage=false
"""Smooth python SDK."""

import asyncio
import base64
import io
import json
import logging
import time
from pathlib import Path
from typing import Any, Literal, Type

import httpx
import requests
from deprecated import deprecated
from pydantic import BaseModel, Field

from ._base import (
  ApiError,
  BaseAsyncTaskHandle,
  BaseClient,
  BaseTaskHandle,
  BrowserProfilesResponse,
  BrowserSessionRequest,
  BrowserSessionResponse,
  BrowserSessionsResponse,
  Certificate,
  Extension,
  ListExtensionsResponse,
  TaskRequest,
  TaskResponse,
  TaskUpdateRequest,
  TimeoutError,
  ToolSignature,
  UploadExtensionResponse,
  UploadFileResponse,
)
from ._tools import AsyncSmoothTool, SmoothTool
from ._utils import encode_url

# Configure logging
logger = logging.getLogger("smooth")


BASE_URL = "https://api.smooth.sh/api/"


# --- Utils ---


def _process_certificates(
  certificates: list[Certificate] | None,
) -> list[dict[str, Any]] | None:
  """Process certificates, converting binary IO to base64-encoded strings.

  Args:
      certificates: List of certificates with file field as string or binary IO.

  Returns:
      List of certificates with file field as base64-encoded string, or None if input is None.
  """
  if certificates is None:
    return None

  processed_certs: list[dict[str, Any]] = []
  for cert in certificates:
    processed_cert = dict(cert)  # Create a copy

    file_content = processed_cert["file"]
    if isinstance(file_content, io.IOBase):
      # Read the binary content and encode to base64
      binary_data = file_content.read()
      processed_cert["file"] = base64.b64encode(binary_data).decode("utf-8")
    elif not isinstance(file_content, str):
      raise TypeError(f"Certificate file must be a string or binary IO, got {type(file_content)}")

    processed_certs.append(processed_cert)

  return processed_certs


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


class TaskHandle(BaseTaskHandle):
  """A handle to a running task."""

  def __init__(self, task_id: str, client: BaseClient, tools: list[SmoothTool] | None = None):
    """Initializes the task handle."""
    super().__init__(task_id)
    self._client = client
    self._tools = {tool.name: tool for tool in (tools or [])}

  def id(self):
    """Returns the task ID."""
    return self._id

  def stop(self):
    """Stops the task."""
    self._client._delete_task(self._id)

  def result(self, timeout: int | None = None, poll_interval: float = 1) -> TaskResponse:
    """Waits for the task to complete and returns the result."""
    if self._task_response and self._task_response.status not in [
      "running",
      "waiting",
    ]:
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
      if task_response.tool_calls:
        for id, tool_call_request in task_response.tool_calls.items():
          if tool_call_request.name:
            self._tools[tool_call_request.name](
              self, id, **json.loads(tool_call_request.input) if tool_call_request.input else {}
            )
      time.sleep(poll_interval)
    raise TimeoutError(f"Task {self.id()} did not complete within {timeout} seconds.")

  def live_url(self, interactive: bool = False, embed: bool = False, timeout: int | None = None):
    """Returns the live URL for the task."""
    if self._task_response and self._task_response.live_url:
      return encode_url(self._task_response.live_url, interactive=interactive, embed=embed)

    start_time = time.time()
    while timeout is None or (time.time() - start_time) < timeout:
      task_response = self._client._get_task(self.id())
      self._task_response = task_response
      if self._task_response.live_url:
        return encode_url(self._task_response.live_url, interactive=interactive, embed=embed)
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
        if not task_response.recording_url:
          raise ApiError(
            status_code=404,
            detail=(
              f"Recording URL not available for task {self.id()}."
              " Set `enable_recording=True` when creating the task to enable it."
            ),
          )
        return task_response.recording_url
      time.sleep(1)
    raise TimeoutError(f"Recording URL not available for task {self.id()}.")

  def downloads_url(self, timeout: int | None = None) -> str:
    """Returns the downloads URL for the task."""
    if self._task_response and self._task_response.downloads_url is not None:
      return self._task_response.downloads_url

    start_time = time.time()
    while timeout is None or (time.time() - start_time) < timeout:
      task_response = self._client._get_task(self.id(), query_params={"downloads": "true"})
      self._task_response = task_response
      if task_response.downloads_url is not None:
        if not task_response.downloads_url:
          raise ApiError(
            status_code=404,
            detail=(
              f"Downloads URL not available for task {self.id()}." " Make sure the task downloaded files during its execution."
            ),
          )
        return task_response.downloads_url
      time.sleep(1)
    raise TimeoutError(f"Downloads URL not available for task {self.id()}.")


class SmoothClient(BaseClient):
  """A synchronous client for the API."""

  def __init__(
    self,
    api_key: str | None = None,
    base_url: str = BASE_URL,
    api_version: str = "v1",
  ):
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
      response = self._session.post(f"{self.base_url}/task", json=payload.model_dump())
      data = self._handle_response(response)
      return TaskResponse(**data["r"])
    except requests.exceptions.RequestException as e:
      logger.error(f"Request failed: {e}")
      raise ApiError(status_code=0, detail=f"Request failed: {str(e)}") from None

  def _get_task(self, task_id: str, query_params: dict[str, Any] | None = None) -> TaskResponse:
    """Retrieves the status and result of a task."""
    if not task_id:
      raise ValueError("Task ID cannot be empty.")

    try:
      url = f"{self.base_url}/task/{task_id}"
      response = self._session.get(url, params=query_params)
      data = self._handle_response(response)
      return TaskResponse(**data["r"])
    except requests.exceptions.RequestException as e:
      logger.error(f"Request failed: {e}")
      raise ApiError(status_code=0, detail=f"Request failed: {str(e)}") from None

  def _update_task(self, task_id: str, payload: TaskUpdateRequest) -> bool:
    """Updates a running task with user input."""
    if not task_id:
      raise ValueError("Task ID cannot be empty.")

    try:
      response = self._session.put(f"{self.base_url}/task/{task_id}", json=payload.model_dump())
      self._handle_response(response)
      return True
    except requests.exceptions.RequestException as e:
      logger.error(f"Request failed: {e}")
      raise ApiError(status_code=0, detail=f"Request failed: {str(e)}") from None

  def _delete_task(self, task_id: str):
    """Deletes a task."""
    if not task_id:
      raise ValueError("Task ID cannot be empty.")

    try:
      response = self._session.delete(f"{self.base_url}/task/{task_id}")
      self._handle_response(response)
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
    enable_recording: bool = True,
    session_id: str | None = None,
    profile_id: str | None = None,
    profile_read_only: bool = False,
    stealth_mode: bool = False,
    proxy_server: str | None = None,
    proxy_username: str | None = None,
    proxy_password: str | None = None,
    certificates: list[Certificate] | None = None,
    use_adblock: bool | None = True,
    additional_tools: dict[str, dict[str, Any] | None] | None = None,
    custom_tools: list[SmoothTool] | None = None,
    experimental_features: dict[str, Any] | None = None,
    extensions: list[str] | None = None,
  ) -> TaskHandle:
    """Runs a task and returns a handle to the task.

    This method submits a task and returns a `TaskHandle` object
    that can be used to get the result of the task.

    Args:
        task: The task to run.
        response_model: If provided, the schema describing the desired output structure.
        url: The starting URL for the task. If not provided, the agent will infer it from the task.
        metadata: A dictionary containing variables or parameters that will be passed to the agent.
        files: A list of file ids to pass to the agent.
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
        proxy_server: Proxy server address to route browser traffic through.
        proxy_username: Proxy server username.
        proxy_password: Proxy server password.
        certificates: List of client certificates to use when accessing secure websites.
          Each certificate is a dictionary with the following fields:
          - `file` (required): p12 file object to be uploaded (e.g., open("cert.p12", "rb")).
          - `password` (optional): Password to decrypt the certificate file, if password-protected.
        use_adblock: Enable adblock for the browser session. Default is True.
        additional_tools: Additional tools to enable for the task.
        custom_tools: Custom tools to register for the task.
        experimental_features: Experimental features to enable for the task.
        extensions: List of extension IDs to load into the browser for this task.

    Returns:
        A handle to the running task.

    Raises:
        ApiException: If the API request fails.
    """
    payload = TaskRequest(
      task=task,
      response_model=response_model if isinstance(response_model, dict | None) else response_model.model_json_schema(),
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
      certificates=_process_certificates(certificates),
      use_adblock=use_adblock,
      additional_tools=additional_tools,
      custom_tools=[tool.signature for tool in custom_tools] if custom_tools else None,
      experimental_features=experimental_features,
      extensions=extensions,
    )
    initial_response = self._submit_task(payload)

    return TaskHandle(initial_response.id, self, tools=custom_tools)

  def tool(self, name: str, description: str, inputs: dict[str, Any], output: str):
    """Decorator to register an asynchronous tool function."""

    def decorator(func: Any):
      async_tool = SmoothTool(
        signature=ToolSignature(name=name, description=description, inputs=inputs, output=output), fn=func
      )
      return async_tool

    return decorator

  def open_session(
    self,
    profile_id: str | None = None,
    session_id: str | None = None,
    live_view: bool = True,
    device: Literal["desktop", "mobile"] = "desktop",
    url: str | None = None,
    proxy_server: str | None = None,
    proxy_username: str | None = None,
    proxy_password: str | None = None,
  ) -> BrowserSessionHandle:
    """Opens an interactive browser instance to interact with a specific browser profile.

    Args:
        profile_id: The profile ID to use for the session. If None, a new profile will be created.
        session_id: (Deprecated, now `profile_id`) The session ID to associate with the browser.
        live_view: Whether to enable live view for the session.
        device: The device type to use for the browser session.
        url: The URL to open in the browser session.
        proxy_server: Proxy server address to route browser traffic through.
        proxy_username: Proxy server username.
        proxy_password: Proxy server password.

    Returns:
        The browser session details, including the live URL.

    Raises:
        ApiException: If the API request fails.
    """
    try:
      response = self._session.post(
        f"{self.base_url}/browser/session",
        json=BrowserSessionRequest(
          profile_id=profile_id or session_id,
          live_view=live_view,
          device=device,
          url=url,
          proxy_server=proxy_server,
          proxy_username=proxy_username,
          proxy_password=proxy_password,
        ).model_dump(),
      )
      data = self._handle_response(response)
      return BrowserSessionHandle(browser_session=BrowserSessionResponse(**data["r"]))
    except requests.exceptions.RequestException as e:
      logger.error(f"Request failed: {e}")
      raise ApiError(status_code=0, detail=f"Request failed: {str(e)}") from None

  def close_session(self, live_id: str):
    """Closes a browser session."""
    try:
      response = self._session.delete(f"{self.base_url}/browser/session/{live_id}")
      self._handle_response(response)
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
      response = self._session.get(f"{self.base_url}/browser/profile")
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
      response = self._session.delete(f"{self.base_url}/browser/profile/{profile_id}")
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

  def upload_extension(self, file: io.IOBase, name: str | None = None) -> UploadExtensionResponse:
    """Upload an extension and return the extension ID."""
    try:
      name = name or getattr(file, "name", None)
      if name is None:
        raise ValueError("Extension name must be provided or the extension object must have a 'name' attribute.")
      files = {"file": (Path(name).name, file)}
      response = self._session.post(f"{self.base_url}/browser/extension", files=files)
      data = self._handle_response(response)
      return UploadExtensionResponse(**data["r"])
    except requests.exceptions.RequestException as e:
      logger.error(f"Request failed: {e}")
      raise ApiError(status_code=0, detail=f"Request failed: {str(e)}") from None

  def list_extensions(self) -> ListExtensionsResponse:
    """List all extensions."""
    try:
      response = self._session.get(f"{self.base_url}/browser/extension")
      data = self._handle_response(response)
      return ListExtensionsResponse(**data["r"])
    except requests.exceptions.RequestException as e:
      logger.error(f"Request failed: {e}")
      raise ApiError(status_code=0, detail=f"Request failed: {str(e)}") from None

  def delete_extension(self, extension_id: str):
    """Delete an extension by its ID."""
    try:
      response = self._session.delete(f"{self.base_url}/browser/extension/{extension_id}")
      self._handle_response(response)
    except requests.exceptions.RequestException as e:
      logger.error(f"Request failed: {e}")
      raise ApiError(status_code=0, detail=f"Request failed: {str(e)}") from None


# --- Asynchronous Client ---


class AsyncTaskHandle(BaseAsyncTaskHandle):
  """An asynchronous handle to a running task."""

  def __init__(self, task_id: str, client: "SmoothAsyncClient", tools: list[AsyncSmoothTool] | None = None):
    """Initializes the asynchronous task handle."""
    super().__init__(task_id)
    self._client = client
    self._tools = {tool.name: tool for tool in (tools or [])}

  async def stop(self):
    """Stops the task."""
    await self._client._delete_task(self._id)

  async def update(self, payload: TaskUpdateRequest) -> bool:
    """Updates a running task with user input."""
    return await self._client._update_task(self._id, payload)

  async def result(self, timeout: int | None = None, poll_interval: float = 1) -> TaskResponse:
    """Waits for the task to complete and returns the result."""
    if self._task_response and self._task_response.status not in [
      "running",
      "waiting",
    ]:
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
      if task_response.tool_calls:
        tasks = [
          await self._tools[tool_call_request.name](
            self, id, **json.loads(tool_call_request.input) if tool_call_request.input else {}
          )
          for id, tool_call_request in task_response.tool_calls.items()
          if tool_call_request.name
        ]
        await asyncio.gather(*tasks)

      await asyncio.sleep(poll_interval)
    raise TimeoutError(f"Task {self.id()} did not complete within {timeout} seconds.")

  async def live_url(self, interactive: bool = False, embed: bool = False, timeout: int | None = None):
    """Returns the live URL for the task."""
    if self._task_response and self._task_response.live_url:
      return encode_url(self._task_response.live_url, interactive=interactive, embed=embed)

    start_time = time.time()
    while timeout is None or (time.time() - start_time) < timeout:
      task_response = await self._client._get_task(self.id())
      self._task_response = task_response
      if self._task_response.live_url:
        return encode_url(self._task_response.live_url, interactive=interactive, embed=embed)
      await asyncio.sleep(1)

    raise TimeoutError(f"Live URL not available for task {self.id()}.")

  async def recording_url(self, timeout: int | None = None) -> str:
    """Returns the recording URL for the task."""
    if self._task_response and self._task_response.recording_url is not None:
      return self._task_response.recording_url

    start_time = time.time()
    while timeout is None or (time.time() - start_time) < timeout:
      task_response = await self._client._get_task(self.id())
      self._task_response = task_response
      if task_response.recording_url is not None:
        if not task_response.recording_url:
          raise ApiError(
            status_code=404,
            detail=(
              f"Recording URL not available for task {self.id()}."
              " Set `enable_recording=True` when creating the task to enable it."
            ),
          )
        return task_response.recording_url
      await asyncio.sleep(1)

    raise TimeoutError(f"Recording URL not available for task {self.id()}.")

  async def downloads_url(self, timeout: int | None = None) -> str:
    """Returns the downloads URL for the task."""
    if self._task_response and self._task_response.downloads_url is not None:
      return self._task_response.downloads_url

    start_time = time.time()
    while timeout is None or (time.time() - start_time) < timeout:
      task_response = await self._client._get_task(self.id(), query_params={"downloads": "true"})
      self._task_response = task_response
      if task_response.downloads_url is not None:
        if not task_response.downloads_url:
          raise ApiError(
            status_code=404,
            detail=(
              f"Downloads URL not available for task {self.id()}." " Make sure the task downloaded files during its execution."
            ),
          )
        return task_response.downloads_url
      await asyncio.sleep(1)

    raise TimeoutError(f"Downloads URL not available for task {self.id()}.")


class SmoothAsyncClient(BaseClient):
  """An asynchronous client for the API."""

  def __init__(
    self,
    api_key: str | None = None,
    base_url: str = BASE_URL,
    api_version: str = "v1",
    timeout: int = 30,
  ):
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
      response = await self._client.post(f"{self.base_url}/task", json=payload.model_dump())
      data = self._handle_response(response)
      return TaskResponse(**data["r"])
    except httpx.RequestError as e:
      logger.error(f"Request failed: {e}")
      raise ApiError(status_code=0, detail=f"Request failed: {str(e)}") from None

  async def _get_task(self, task_id: str, query_params: dict[str, Any] | None = None) -> TaskResponse:
    """Retrieves the status and result of a task asynchronously."""
    if not task_id:
      raise ValueError("Task ID cannot be empty.")

    try:
      url = f"{self.base_url}/task/{task_id}"
      response = await self._client.get(url, params=query_params)
      data = self._handle_response(response)
      return TaskResponse(**data["r"])
    except httpx.RequestError as e:
      logger.error(f"Request failed: {e}")
      raise ApiError(status_code=0, detail=f"Request failed: {str(e)}") from None

  async def _update_task(self, task_id: str, payload: TaskUpdateRequest) -> bool:
    """Updates a running task with user input asynchronously."""
    if not task_id:
      raise ValueError("Task ID cannot be empty.")

    try:
      response = await self._client.put(f"{self.base_url}/task/{task_id}", json=payload.model_dump())
      self._handle_response(response)
      return True
    except httpx.RequestError as e:
      logger.error(f"Request failed: {e}")
      raise ApiError(status_code=0, detail=f"Request failed: {str(e)}") from None

  async def _delete_task(self, task_id: str):
    """Deletes a task asynchronously."""
    if not task_id:
      raise ValueError("Task ID cannot be empty.")

    try:
      response = await self._client.delete(f"{self.base_url}/task/{task_id}")
      self._handle_response(response)
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
    enable_recording: bool = True,
    session_id: str | None = None,
    profile_id: str | None = None,
    profile_read_only: bool = False,
    stealth_mode: bool = False,
    proxy_server: str | None = None,
    proxy_username: str | None = None,
    proxy_password: str | None = None,
    certificates: list[Certificate] | None = None,
    use_adblock: bool | None = True,
    additional_tools: dict[str, dict[str, Any] | None] | None = None,
    custom_tools: list[AsyncSmoothTool] | None = None,
    experimental_features: dict[str, Any] | None = None,
  ) -> AsyncTaskHandle:
    """Runs a task and returns a handle to the task asynchronously.

    This method submits a task and returns an `AsyncTaskHandle` object
    that can be used to get the result of the task.

    Args:
        task: The task to run.
        response_model: If provided, the schema describing the desired output structure.
        url: The starting URL for the task. If not provided, the agent will infer it from the task.
        metadata: A dictionary containing variables or parameters that will be passed to the agent.
        files: A list of file ids to pass to the agent.
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
        proxy_server: Proxy server address to route browser traffic through.
        proxy_username: Proxy server username.
        proxy_password: Proxy server password.
        certificates: List of client certificates to use when accessing secure websites.
          Each certificate is a dictionary with the following fields:
          - `file` (required): p12 file object to be uploaded (e.g., open("cert.p12", "rb")).
          - `password` (optional): Password to decrypt the certificate file.
        use_adblock: Enable adblock for the browser session. Default is True.
        additional_tools: Additional tools to enable for the task.
        custom_tools: Custom tools to register for the task.
        experimental_features: Experimental features to enable for the task.

    Returns:
        A handle to the running task.

    Raises:
        ApiException: If the API request fails.
    """
    payload = TaskRequest(
      task=task,
      response_model=response_model if isinstance(response_model, dict | None) else response_model.model_json_schema(),
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
      certificates=_process_certificates(certificates),
      use_adblock=use_adblock,
      additional_tools=additional_tools,
      custom_tools=[tool.signature for tool in custom_tools] if custom_tools else None,
      experimental_features=experimental_features,
    )

    initial_response = await self._submit_task(payload)
    return AsyncTaskHandle(initial_response.id, self, tools=custom_tools)

  def tool(self, name: str, description: str, inputs: dict[str, Any], output: str):
    """Decorator to register an asynchronous tool function."""

    def decorator(func: Any):
      async_tool = AsyncSmoothTool(ToolSignature(name=name, description=description, inputs=inputs, output=output), fn=func)
      return async_tool

    return decorator

  async def open_session(
    self,
    profile_id: str | None = None,
    session_id: str | None = None,
    live_view: bool = True,
    device: Literal["desktop", "mobile"] = "desktop",
    url: str | None = None,
    proxy_server: str | None = None,
    proxy_username: str | None = None,
    proxy_password: str | None = None,
  ) -> BrowserSessionHandle:
    """Opens an interactive browser instance asynchronously.

    Args:
        profile_id: The profile ID to use for the session. If None, a new profile will be created.
        session_id: (Deprecated, now `profile_id`) The session ID to associate with the browser.
        live_view: Whether to enable live view for the session.
        device: The device type to use for the session. Defaults to "desktop".
        url: The URL to open in the browser session.
        proxy_server: Proxy server address to route browser traffic through.
        proxy_username: Proxy server username.
        proxy_password: Proxy server password.

    Returns:
        The browser session details, including the live URL.

    Raises:
        ApiException: If the API request fails.
    """
    try:
      response = await self._client.post(
        f"{self.base_url}/browser/session",
        json=BrowserSessionRequest(
          profile_id=profile_id or session_id,
          live_view=live_view,
          device=device,
          url=url,
          proxy_server=proxy_server,
          proxy_username=proxy_username,
          proxy_password=proxy_password,
        ).model_dump(),
      )
      data = self._handle_response(response)
      return BrowserSessionHandle(browser_session=BrowserSessionResponse(**data["r"]))
    except httpx.RequestError as e:
      logger.error(f"Request failed: {e}")
      raise ApiError(status_code=0, detail=f"Request failed: {str(e)}") from None

  async def close_session(self, live_id: str):
    """Closes a browser session."""
    try:
      response = await self._client.delete(f"{self.base_url}/browser/session/{live_id}")
      self._handle_response(response)
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
      response = await self._client.get(f"{self.base_url}/browser/profile")
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
      response = await self._client.delete(f"{self.base_url}/browser/profile/{profile_id}")
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

      if purpose:
        data = {"file_purpose": purpose}
      else:
        data = None

      files = {"file": (Path(name).name, file)}
      response = await self._client.post(f"{self.base_url}/file", files=files, data=data)  # type: ignore
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

  async def upload_extension(self, file: io.IOBase, name: str | None = None) -> UploadExtensionResponse:
    """Upload an extension and return the extension ID."""
    try:
      name = name or getattr(file, "name", None)
      if name is None:
        raise ValueError("File name must be provided or the file object must have a 'name' attribute.")
      files = {"file": (Path(name).name, file)}
      response = await self._client.post(f"{self.base_url}/browser/extension", files=files)  # type: ignore
      data = self._handle_response(response)
      return UploadExtensionResponse(**data["r"])
    except httpx.RequestError as e:
      logger.error(f"Request failed: {e}")
      raise ApiError(status_code=0, detail=f"Request failed: {str(e)}") from None

  async def list_extensions(self) -> ListExtensionsResponse:
    """List all extensions."""
    try:
      response = await self._client.get(f"{self.base_url}/browser/extension")
      data = self._handle_response(response)
      return ListExtensionsResponse(**data["r"])
    except httpx.RequestError as e:
      logger.error(f"Request failed: {e}")
      raise ApiError(status_code=0, detail=f"Request failed: {str(e)}") from None

  async def delete_extension(self, extension_id: str):
    """Delete an extension by its ID."""
    try:
      response = await self._client.delete(f"{self.base_url}/browser/extension/{extension_id}")
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
  "UploadExtensionResponse",
  "ListExtensionsResponse",
  "Extension",
  "Certificate",
  "ApiError",
  "TimeoutError",
]
