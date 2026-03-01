# pyright: reportPrivateUsage=false
import asyncio
import inspect
import io
import os
import secrets
import threading
from pathlib import Path
from typing import Any, Callable, Coroutine, Literal, Sequence, Type, TypedDict, TypeVar, cast

import aiohttp
from aiohttp_retry import ExponentialRetry, RetryClient
from deprecated import deprecated
from pydantic import BaseModel

from smooth._interface import AsyncSessionHandle, AsyncTaskHandle, BrowserSessionHandle, SessionHandle, TaskHandle

from ._config import BASE_URL, SDK_VERSION
from ._exceptions import ApiError
from ._telemetry import Telemetry, track
from ._tools import AsyncSmoothTool, SmoothTool
from ._utils import logger, process_certificates
from .models import (
  BrowserSessionRequest,
  BrowserSessionResponse,
  Certificate,
  DeviceType,
  Extension,
  ProfileRequest,
  ProfileResponse,
  TaskEvent,
  TaskEventResponse,
  TaskRequest,
  TaskResponse,
  TaskUpdateRequest,
  ToolSignature,
  UploadExtensionResponse,
  UploadFileResponse,
)

T = TypeVar("T")


class ProxyConfig(TypedDict):
  """Configuration returned by start_proxy() for use with session methods."""

  proxy_server: str
  proxy_username: str
  proxy_password: str


def _get_proxy_url(live_url: str) -> str:
  import base64
  from urllib.parse import parse_qs, urlparse

  parsed = urlparse(live_url)
  query = parse_qs(parsed.query)
  q = query.get("b", [None])[0]
  if q:
    # Add padding if needed (base64 strings must be multiple of 4)
    padded = q + "=" * (-len(q) % 4)
    # Use urlsafe_b64decode for URL-safe base64 encoding
    proxy_url = base64.urlsafe_b64decode(padded).decode().split("https://", 1)[-1]
    return proxy_url.replace("browser-live", "browser-proxy").split("?", 1)[0].strip("/")
  else:
    raise RuntimeError("No proxy URL provided.")


# --- Base Client ---


class BaseClient:
  """Base client for handling common API interactions."""

  def __init__(
    self,
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

    self.api_key = api_key
    self.base_url = f"{base_url.rstrip('/')}/{api_version}"
    self.headers = {
      "apikey": self.api_key,
      "User-Agent": f"smooth-python-sdk/{SDK_VERSION}",
    }

    Telemetry.get().init(self.api_key)

  async def _handle_response(self, response: aiohttp.ClientResponse) -> dict[str, Any]:
    """Handles HTTP responses and raises exceptions for errors."""
    if 200 <= response.status < 300:
      try:
        return await response.json()
      except ValueError as e:
        logger.error(f"Failed to parse JSON response: {e}")
        raise ApiError(
          status_code=response.status,
          detail="Invalid JSON response from server",
        ) from None

    # Handle error responses
    error_data = None
    try:
      error_data = await response.json()
      detail = error_data.get("detail", await response.text())
    except ValueError:
      text = await response.text()
      detail = text or f"HTTP {response.status} error"

    logger.error(f"API error: {response.status} - {detail}")
    raise ApiError(status_code=response.status, detail=detail, response_data=error_data)

  def _submit_task(self, payload: TaskRequest) -> TaskResponse:
    raise NotImplementedError

  def _get_task(self, task_id: str, query_params: dict[str, Any] | None = None) -> TaskResponse:
    raise NotImplementedError

  def _delete_task(self, task_id: str) -> None:
    raise NotImplementedError

  def _update_task(self, task_id: str, payload: "TaskUpdateRequest") -> bool:
    raise NotImplementedError

  def _send_task_event(self, task_id: str, event: TaskEvent) -> TaskEventResponse:
    raise NotImplementedError


class SmoothClient(BaseClient):
  """A synchronous client for the API (wraps SmoothAsyncClient)."""

  def __init__(
    self,
    api_key: str | None = None,
    base_url: str = BASE_URL,
    api_version: str = "v1",
    timeout: int = 30,
    retries: int = 3,
  ):
    """Initializes the synchronous client.

    Args:
        api_key: API key for authentication.
        base_url: Base URL for the API.
        api_version: API version.
        timeout: Request timeout in seconds.
        retries: Number of retry attempts for failed requests (0 to disable).
    """
    super().__init__(api_key, base_url, api_version)
    self._async_client = SmoothAsyncClient(api_key, base_url, api_version, timeout, retries)

    # Create persistent event loop in background thread
    self._loop = asyncio.new_event_loop()
    self._loop_thread = threading.Thread(target=self._run_loop, daemon=True)
    self._loop_thread.start()

  def session(
    self,
    url: str | None = None,
    files: list[str] | None = None,
    agent: Literal["smooth"] = "smooth",
    device: DeviceType = "desktop",
    allowed_urls: list[str] | None = None,
    enable_recording: bool = True,
    profile_id: str | None = None,
    profile_read_only: bool = False,
    stealth_mode: bool = False,
    proxy_server: str | None = None,
    proxy_username: str | None = None,
    proxy_password: str | None = None,
    certificates: list[Certificate | dict[str, Any]] | None = None,
    use_adblock: bool | None = True,
    use_captcha_solver: bool | None = True,
    additional_tools: dict[str, dict[str, Any] | None] | None = None,
    custom_tools: Sequence[SmoothTool | dict[str, Any]] | None = None,
    experimental_features: dict[str, Any] | None = None,
    extensions: list[str] | None = None,
    show_cursor: bool = False,
  ) -> SessionHandle:
    """Opens a browser session."""
    # Handle proxy_server="self" - auto-start local proxy tunnel
    self_proxy = proxy_server == "self"
    if self_proxy and not proxy_password:
      proxy_password = secrets.token_urlsafe(12)

    task_handle = self.run(
      task=None,  # type: ignore
      url=url,
      files=files,
      agent=agent,
      device=device,
      allowed_urls=allowed_urls,
      enable_recording=enable_recording,
      profile_id=profile_id,
      profile_read_only=profile_read_only,
      stealth_mode=stealth_mode,
      proxy_server=proxy_server,
      proxy_username=proxy_username,
      proxy_password=proxy_password,
      certificates=certificates,
      use_adblock=use_adblock,
      use_captcha_solver=use_captcha_solver,
      additional_tools=additional_tools,
      custom_tools=custom_tools,
      experimental_features=experimental_features,
      extensions=extensions,
      show_cursor=show_cursor,
    )

    tools = cast(dict[str, SmoothTool] | None, task_handle._async_handle._tools)
    handle = SessionHandle(task_handle._id, self, tools=list(tools.values()) if tools else None)

    # Auto-start proxy immediately if configured
    if self_proxy:
      try:
        proxy_url = _get_proxy_url(handle.live_url(timeout=30))
        handle._start_proxy(proxy_url, cast(str, proxy_password))
      except Exception as e:
        raise RuntimeError("Failed to start self-proxy.") from e

    return handle

  def run(
    self,
    task: str,
    response_model: dict[str, Any] | Type[BaseModel] | None = None,
    url: str | None = None,
    metadata: dict[str, str | int | float | bool] | None = None,
    files: list[str] | None = None,
    agent: Literal["smooth"] = "smooth",
    max_steps: int = 32,
    device: DeviceType = "desktop",
    allowed_urls: list[str] | None = None,
    enable_recording: bool = True,
    session_id: str | None = None,
    profile_id: str | None = None,
    profile_read_only: bool = False,
    stealth_mode: bool = False,
    proxy_server: str | None = None,
    proxy_username: str | None = None,
    proxy_password: str | None = None,
    certificates: list[Certificate | dict[str, Any]] | None = None,
    use_adblock: bool | None = True,
    use_captcha_solver: bool | None = True,
    additional_tools: dict[str, dict[str, Any] | None] | None = None,
    custom_tools: Sequence[SmoothTool | dict[str, Any]] | None = None,
    experimental_features: dict[str, Any] | None = None,
    extensions: list[str] | None = None,
    show_cursor: bool = False,
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
        device: Device type for the task. Default is desktop.
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
        use_captcha_solver: Enable captcha solver for the browser session. Default is True.
        additional_tools: Additional tools to enable for the task.
        custom_tools: Custom tools to register for the task. Use the @client.tool decorator or SmoothTool class.
        experimental_features: Experimental features to enable for the task.
        extensions: List of extension IDs to load into the browser for this task.
        show_cursor: Show mouse cursor. Default is False.

    Returns:
        A handle to the running task.

    Raises:
        ApiException: If the API request fails.
    """
    custom_tools_ = (
      [tool if isinstance(tool, SmoothTool) else SmoothTool(**tool) for tool in custom_tools] if custom_tools else None
    )

    # Handle proxy_server="self" - auto-generate password if not provided
    if proxy_server == "self" and not proxy_password:
      proxy_password = secrets.token_urlsafe(12)

    async_handle = self._run_async(
      self._async_client.run(
        task=task,
        response_model=response_model,
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
        certificates=certificates,
        use_adblock=use_adblock,
        use_captcha_solver=use_captcha_solver,
        additional_tools=additional_tools,
        custom_tools=custom_tools_,
        experimental_features=experimental_features,
        extensions=extensions,
        show_cursor=show_cursor,
      )
    )

    return TaskHandle(async_handle._id, self, tools=custom_tools_)

  def tool(
    self,
    name: str,
    description: str,
    inputs: dict[str, Any],
    output: str,
    essential: bool = True,
    error_message: str | None = None,
  ):
    """Decorator to register a tool function."""

    def decorator(func: Callable[..., Any]):
      if inspect.iscoroutinefunction(func):
        raise TypeError(
          f"SmoothClient.tool cannot wrap async function {func.__name__}. Use SmoothAsyncClient if you need async support."
        )
      tool = SmoothTool(
        signature=ToolSignature(name=name, description=description, inputs=inputs, output=output),
        fn=func,
        essential=essential,
        error_message=error_message,
      )
      return tool

    return decorator

  # --- Profile Methods --- #

  def create_profile(self, profile_id: str | None = None) -> ProfileResponse:
    """Creates a new browser profile.

    Args:
        profile_id: Optional custom ID for the profile. If not provided, a random ID will be generated.

    Returns:
        The created browser profile.
    """
    return self._run_async(self._async_client.create_profile(profile_id))

  def list_profiles(self):
    """Lists all browser profiles for the user.

    Returns:
        A list of existing browser profiles.
    """
    return self._run_async(self._async_client.list_profiles())

  def delete_profile(self, profile_id: str):
    """Delete a browser profile.

    Args:
        profile_id: The ID of the profile to delete.

    Raises:
        ApiException: If the API request fails.
    """
    return self._run_async(self._async_client.delete_profile(profile_id))

  # --- File Uploads Methods --- #

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
        ApiException: If the API request fails.
    """
    return self._run_async(self._async_client.upload_file(file, name, purpose))

  def delete_file(self, file_id: str):
    """Delete a file by its ID."""
    return self._run_async(self._async_client.delete_file(file_id))

  # --- Extension Methods --- #

  def upload_extension(self, file: io.IOBase, name: str | None = None) -> UploadExtensionResponse:
    """Upload an extension and return the extension ID."""
    return self._run_async(self._async_client.upload_extension(file, name))

  def list_extensions(self):
    """List all extensions."""
    return self._run_async(self._async_client.list_extensions())

  def delete_extension(self, extension_id: str):
    """Delete an extension by its ID."""
    return self._run_async(self._async_client.delete_extension(extension_id))

  # --- Proxy Methods --- #

  # def start_proxy(
  #   self,
  #   provider: Literal["cloudflare", "serveo", "microsoft"] = "cloudflare",
  #   port: int = 8888,
  #   timeout: int = 30,
  #   verbose: bool = False,
  #   username: str | None = None,
  #   password: str | None = None,
  # ) -> ProxyConfig:
  #   """Start a local proxy server with public tunnel exposure.

  #   The proxy runs in a background thread and can be stopped with stop_proxy().
  #   Returns a dict with proxy credentials that can be unpacked into session/run methods.

  #   Example:
  #       proxy_config = client.start_proxy()
  #       client.session(**proxy_config)
  #       # ... use the session ...
  #       client.stop_proxy()

  #   Args:
  #       provider: Tunnel provider ("cloudflare", "serveo", or "microsoft").
  #       port: Local port for the proxy server.
  #       timeout: Tunnel timeout in seconds.
  #       verbose: Enable verbose output.
  #       username: Optional proxy username. If not provided, randomly generated.
  #       password: Optional proxy password. If not provided, randomly generated.

  #   Returns:
  #       ProxyConfig dict with keys: proxy_server, proxy_username, proxy_password

  #   Raises:
  #       RuntimeError: If proxy is already running or fails to start.
  #   """
  #   return self._async_client.start_proxy(
  #     provider=provider,
  #     port=port,
  #     timeout=timeout,
  #     verbose=verbose,
  #     username=username,
  #     password=password,
  #   )

  # def stop_proxy(self):
  #   """Stop the running proxy server.

  #   Raises:
  #       RuntimeError: If no proxy is currently running.
  #   """
  #   return self._async_client.stop_proxy()

  # --- Private Methods ---

  def _run_loop(self):
    """Run the event loop in a background thread."""
    asyncio.set_event_loop(self._loop)
    self._loop.run_forever()

  def _run_async(self, coro: Coroutine[Any, Any, T]) -> T:
    """Run an async coroutine in the background loop and return the result."""
    future = asyncio.run_coroutine_threadsafe(coro, self._loop)
    return future.result()

  def __enter__(self):
    """Enters the synchronous context manager."""
    self._run_async(self._async_client.__aenter__())
    return self

  def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any):
    """Exits the synchronous context manager."""
    self._run_async(self._async_client.__aexit__(exc_type, exc_val, exc_tb))

  def _submit_task(self, payload: TaskRequest) -> TaskResponse:
    """Submits a task to be run."""
    return self._run_async(self._async_client._submit_task(payload))

  def _get_task(self, task_id: str, query_params: dict[str, Any] | None = None) -> TaskResponse:
    """Retrieves the status and result of a task."""
    return self._run_async(self._async_client._get_task(task_id, query_params))

  @deprecated("update_task is deprecated")
  def _update_task(self, task_id: str, payload: TaskUpdateRequest) -> bool:
    """Updates a running task with user input."""
    return self._run_async(self._async_client._update_task(task_id, payload))

  def _send_task_event(self, task_id: str, event: TaskEvent) -> TaskEventResponse:
    """Sends an event to a running task."""
    return self._run_async(self._async_client._send_task_event(task_id, event))

  def _delete_task(self, task_id: str):
    """Deletes a task."""
    self._run_async(self._async_client._delete_task(task_id))

  def __del__(self):
    """Cleanup the event loop when the client is destroyed."""
    try:
      if hasattr(self, "_loop") and self._loop.is_running():
        self._loop.call_soon_threadsafe(self._loop.stop)
    except Exception:
      pass

  # --- Deprecated Methods ---

  @deprecated("open_session is deprecated, use session instead")
  def open_session(
    self,
    profile_id: str | None = None,
    session_id: str | None = None,
    live_view: bool = True,
    device: DeviceType = "desktop",
    url: str | None = None,
    proxy_server: str | None = None,
    proxy_username: str | None = None,
    proxy_password: str | None = None,
    extensions: list[str] | None = None,
  ):
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
        extensions: List of extensions to install for the browser session.

    Returns:
        The browser session details, including the live URL.

    Raises:
        ApiException: If the API request fails.
    """
    return self._run_async(
      self._async_client.open_session(
        profile_id=profile_id,
        session_id=session_id,
        live_view=live_view,
        device=device,
        url=url,
        proxy_server=proxy_server,
        proxy_username=proxy_username,
        proxy_password=proxy_password,
        extensions=extensions,
      )
    )

  @deprecated("close_session is deprecated")
  def close_session(self, live_id: str):
    """Closes a browser session."""
    self._run_async(self._async_client.close_session(live_id))

  @deprecated("list_sessions is deprecated, use list_profiles instead")
  def list_sessions(self):
    """Lists all browser profiles for the user."""
    return self.list_profiles()

  @deprecated("delete_session is deprecated, use delete_profile instead")
  def delete_session(self, session_id: str):
    """Delete a browser profile."""
    self.delete_profile(session_id)


# --- Asynchronous Client ---


class SmoothAsyncClient(BaseClient):
  """An asynchronous client for the API."""

  def __init__(
    self,
    api_key: str | None = None,
    base_url: str = BASE_URL,
    api_version: str = "v1",
    timeout: int = 30,
    retries: int = 3,
  ):
    """Initializes the asynchronous client.

    Args:
        api_key: API key for authentication.
        base_url: Base URL for the API.
        api_version: API version.
        timeout: Request timeout in seconds.
        retries: Number of retry attempts for failed requests (0 to disable).
    """
    super().__init__(api_key, base_url, api_version)
    self._timeout = aiohttp.ClientTimeout(total=timeout)
    self._retries = retries
    self._client: aiohttp.ClientSession | RetryClient | None = None
    self._retry_client: RetryClient | None = None

  @track(
    "sdk.session",
    properties_fn=lambda a, kw: {
      "url": kw.get("url") or (a[1] if len(a) > 1 else None),
      "device": kw.get("device", "desktop"),
      "profile_id": kw.get("profile_id"),
      "stealth_mode": kw.get("stealth_mode", False),
      "proxy_server": kw.get("proxy_server"),
    },
  )
  async def session(
    self,
    url: str | None = None,
    files: list[str] | None = None,
    agent: Literal["smooth"] = "smooth",
    device: DeviceType = "desktop",
    allowed_urls: list[str] | None = None,
    enable_recording: bool = True,
    profile_id: str | None = None,
    profile_read_only: bool = False,
    stealth_mode: bool = False,
    proxy_server: str | None = None,
    proxy_username: str | None = None,
    proxy_password: str | None = None,
    certificates: list[Certificate | dict[str, Any]] | None = None,
    use_adblock: bool | None = True,
    use_captcha_solver: bool | None = True,
    additional_tools: dict[str, dict[str, Any] | None] | None = None,
    custom_tools: Sequence[AsyncSmoothTool | dict[str, Any]] | None = None,
    experimental_features: dict[str, Any] | None = None,
    extensions: list[str] | None = None,
    show_cursor: bool = False,
  ):
    """Opens a browser session."""
    # Handle proxy_server="self" - auto-start local proxy tunnel
    self_proxy = proxy_server == "self"
    if self_proxy and proxy_password is None:
      proxy_password = secrets.token_urlsafe(12)

    task_handle = await self.run(
      task=None,  # type: ignore
      url=url,
      files=files,
      agent=agent,
      device=device,
      allowed_urls=allowed_urls,
      enable_recording=enable_recording,
      profile_id=profile_id,
      profile_read_only=profile_read_only,
      stealth_mode=stealth_mode,
      proxy_server=proxy_server,
      proxy_username=proxy_username,
      proxy_password=proxy_password,
      certificates=certificates,
      use_adblock=use_adblock,
      use_captcha_solver=use_captcha_solver,
      additional_tools=additional_tools,
      custom_tools=custom_tools,
      experimental_features=experimental_features,
      extensions=extensions,
      show_cursor=show_cursor,
    )

    handle = AsyncSessionHandle(task_handle._id, self, tools=list(task_handle._tools.values()) if task_handle._tools else None)

    # Auto-start proxy immediately if configured
    if self_proxy:
      try:
        proxy_url = _get_proxy_url(await handle.live_url(timeout=30))
        handle._start_proxy(proxy_url, cast(str, proxy_password))
      except Exception as e:
        raise RuntimeError("Failed to start self-proxy.") from e

    return handle

  @track(
    "sdk.run",
    properties_fn=lambda a, kw: {
      "task": kw.get("task") or (a[1] if len(a) > 1 else None),
      "url": kw.get("url"),
      "device": kw.get("device", "desktop"),
      "max_steps": kw.get("max_steps", 32),
      "profile_id": kw.get("profile_id"),
      "stealth_mode": kw.get("stealth_mode", False),
      "use_adblock": kw.get("use_adblock", True),
      "has_response_model": kw.get("response_model") is not None,
      "has_custom_tools": kw.get("custom_tools") is not None,
    },
  )
  async def run(
    self,
    task: str,
    response_model: dict[str, Any] | Type[BaseModel] | None = None,
    url: str | None = None,
    metadata: dict[str, str | int | float | bool] | None = None,
    files: list[str] | None = None,
    agent: Literal["smooth"] = "smooth",
    max_steps: int = 32,
    device: DeviceType = "desktop",
    allowed_urls: list[str] | None = None,
    enable_recording: bool = True,
    session_id: str | None = None,
    profile_id: str | None = None,
    profile_read_only: bool = False,
    stealth_mode: bool = False,
    proxy_server: str | None = None,
    proxy_username: str | None = None,
    proxy_password: str | None = None,
    certificates: list[Certificate | dict[str, Any]] | None = None,
    use_adblock: bool | None = True,
    use_captcha_solver: bool | None = True,
    additional_tools: dict[str, dict[str, Any] | None] | None = None,
    custom_tools: Sequence[AsyncSmoothTool | dict[str, Any]] | None = None,
    experimental_features: dict[str, Any] | None = None,
    extensions: list[str] | None = None,
    show_cursor: bool = False,
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
        device: Device type for the task. Default is desktop.
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
        use_captcha_solver: Enable captcha solver for the browser session. Default is True.
        additional_tools: Additional tools to enable for the task.
        custom_tools: Custom tools to register for the task.
        experimental_features: Experimental features to enable for the task.
        extensions: List of extension IDs to load into the browser for this task.
        show_cursor: Show mouse cursor. Default is False.

    Returns:
        A handle to the running task.

    Raises:
        ApiException: If the API request fails.
    """
    # Handle proxy_server="self" - auto-generate password if not provided
    if proxy_server == "self" and proxy_password is None:
      proxy_password = secrets.token_urlsafe(12)

    certificates_ = process_certificates(certificates)
    custom_tools_ = (
      [tool if isinstance(tool, AsyncSmoothTool) else AsyncSmoothTool(**tool) for tool in custom_tools]
      if custom_tools
      else None
    )

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
      certificates=certificates_,
      use_adblock=use_adblock,
      use_captcha_solver=use_captcha_solver,
      additional_tools=additional_tools,
      custom_tools=[tool.signature for tool in custom_tools_] if custom_tools_ else None,
      experimental_features=experimental_features,
      extensions=extensions,
      show_cursor=show_cursor,
    )

    initial_response = await self._submit_task(payload)
    return AsyncTaskHandle(initial_response.id, self, tools=custom_tools_)

  def tool(
    self,
    name: str,
    description: str,
    inputs: dict[str, Any],
    output: str,
    essential: bool = True,
    error_message: str | None = None,
  ):
    """Decorator to register an asynchronous tool function."""

    def decorator(func: Callable[..., Coroutine[Any, Any, Any]]):
      if not inspect.iscoroutinefunction(func):
        raise TypeError(f"SmoothAsyncClient.tool cannot wrap non-async function {func.__name__}. Custom tools must be async.")
      async_tool = AsyncSmoothTool(
        signature=ToolSignature(name=name, description=description, inputs=inputs, output=output),
        fn=func,
        essential=essential,
        error_message=error_message,
      )
      return async_tool

    return decorator

  async def close(self):
    """Closes the async client session."""
    if self._retry_client is not None:
      await self._retry_client.close()
      self._retry_client = None
    if self._client is not None:
      await self._client.close()
      self._client = None

  # --- Profile Methods --- #

  @track(
    "sdk.create_profile", properties_fn=lambda a, kw: {"profile_id": kw.get("profile_id") or (a[1] if len(a) > 1 else None)}
  )
  async def create_profile(self, profile_id: str | None = None) -> ProfileResponse:
    """Creates a new browser profile.

    Args:
        profile_id: Optional custom ID for the profile. If not provided, a random ID will be generated.

    Returns:
        The created browser profile.

    Raises:
        ApiException: If the API request fails.
    """
    try:
      session = await self._ensure_session()
      async with session.post(f"{self.base_url}/profile", json=ProfileRequest(id=profile_id).model_dump()) as response:
        data = await self._handle_response(response)
        return ProfileResponse(**data["r"])
    except aiohttp.ClientError as e:
      logger.error(f"Request failed: {e}")
      raise ApiError(status_code=0, detail=f"Request failed: {str(e)}") from None

  @track("sdk.list_profiles")
  async def list_profiles(self):
    """Lists all browser profiles for the user.

    Returns:
        A list of existing browser profiles.

    Raises:
        ApiException: If the API request fails.
    """
    try:
      session = await self._ensure_session()
      async with session.get(f"{self.base_url}/profile") as response:
        data = await self._handle_response(response)
        return [ProfileResponse(**d) for d in data["r"]]
    except aiohttp.ClientError as e:
      logger.error(f"Request failed: {e}")
      raise ApiError(status_code=0, detail=f"Request failed: {str(e)}") from None

  @track(
    "sdk.delete_profile", properties_fn=lambda a, kw: {"profile_id": kw.get("profile_id") or (a[1] if len(a) > 1 else None)}
  )
  async def delete_profile(self, profile_id: str):
    """Delete a browser profile.

    Args:
        profile_id: The ID of the profile to delete.

    Raises:
        ApiException: If the API request fails.
    """
    try:
      session = await self._ensure_session()
      async with session.delete(f"{self.base_url}/profile/{profile_id}") as response:
        await self._handle_response(response)
    except aiohttp.ClientError as e:
      logger.error(f"Request failed: {e}")
      raise ApiError(status_code=0, detail=f"Request failed: {str(e)}") from None

  # --- File Uploads Methods --- #

  @track("sdk.upload_file", properties_fn=lambda a, kw: {"name": kw.get("name"), "purpose": kw.get("purpose")})
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

      session = await self._ensure_session()
      form_data = aiohttp.FormData()
      form_data.add_field("file", file, filename=Path(name).name)
      if purpose:
        form_data.add_field("file_purpose", purpose)

      async with session.post(f"{self.base_url}/file", data=form_data) as response:
        data = await self._handle_response(response)
        return UploadFileResponse(**data["r"])
    except aiohttp.ClientError as e:
      logger.error(f"Request failed: {e}")
      raise ApiError(status_code=0, detail=f"Request failed: {str(e)}") from None

  @track("sdk.delete_file", properties_fn=lambda a, kw: {"file_id": kw.get("file_id") or (a[1] if len(a) > 1 else None)})
  async def delete_file(self, file_id: str):
    """Delete a file by its ID."""
    try:
      session = await self._ensure_session()
      async with session.delete(f"{self.base_url}/file/{file_id}") as response:
        await self._handle_response(response)
    except aiohttp.ClientError as e:
      logger.error(f"Request failed: {e}")
      raise ApiError(status_code=0, detail=f"Request failed: {str(e)}") from None

  # --- Extension Methods --- #

  @track("sdk.upload_extension", properties_fn=lambda a, kw: {"name": kw.get("name")})
  async def upload_extension(self, file: io.IOBase, name: str | None = None) -> UploadExtensionResponse:
    """Upload an extension and return the extension ID."""
    try:
      name = name or getattr(file, "name", None)
      if name is None:
        raise ValueError("File name must be provided or the file object must have a 'name' attribute.")

      session = await self._ensure_session()
      form_data = aiohttp.FormData()
      form_data.add_field("file", file, filename=Path(name).name)

      async with session.post(f"{self.base_url}/extension", data=form_data) as response:
        data = await self._handle_response(response)
        return UploadExtensionResponse(**data["r"])
    except aiohttp.ClientError as e:
      logger.error(f"Request failed: {e}")
      raise ApiError(status_code=0, detail=f"Request failed: {str(e)}") from None

  @track("sdk.list_extensions")
  async def list_extensions(self):
    """List all extensions."""
    try:
      session = await self._ensure_session()
      async with session.get(f"{self.base_url}/extension") as response:
        data = await self._handle_response(response)
        return [Extension(**d) for d in data["r"]]
    except aiohttp.ClientError as e:
      logger.error(f"Request failed: {e}")
      raise ApiError(status_code=0, detail=f"Request failed: {str(e)}") from None

  @track(
    "sdk.delete_extension",
    properties_fn=lambda a, kw: {"extension_id": kw.get("extension_id") or (a[1] if len(a) > 1 else None)},
  )
  async def delete_extension(self, extension_id: str):
    """Delete an extension by its ID."""
    try:
      session = await self._ensure_session()
      async with session.delete(f"{self.base_url}/extension/{extension_id}") as response:
        await self._handle_response(response)
    except aiohttp.ClientError as e:
      logger.error(f"Request failed: {e}")
      raise ApiError(status_code=0, detail=f"Request failed: {str(e)}") from None

  # --- Private Methods ---

  async def __aenter__(self):
    """Enters the asynchronous context manager."""
    self._client = aiohttp.ClientSession(headers=self.headers, timeout=self._timeout)
    if self._retries > 0:
      retry_options = ExponentialRetry(
        attempts=self._retries + 1,
        start_timeout=0.5,
        max_timeout=10.0,
        exceptions={aiohttp.ServerDisconnectedError, aiohttp.ClientConnectorError, ConnectionResetError, TimeoutError},
      )
      self._retry_client = RetryClient(client_session=self._client, retry_options=retry_options)
    return self

  async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any):
    """Exits the asynchronous context manager."""
    await self.close()

  async def _ensure_session(self) -> aiohttp.ClientSession | RetryClient:
    """Ensure session exists, creating it if necessary."""
    if self._client is None:
      await self.__aenter__()
    self._client = cast(aiohttp.ClientSession | RetryClient, self._client)
    return self._retry_client if self._retry_client else self._client

  async def _submit_task(self, payload: TaskRequest) -> TaskResponse:
    """Submits a task to be run asynchronously."""
    try:
      session = await self._ensure_session()
      async with session.post(f"{self.base_url}/task", json=payload.model_dump()) as response:
        data = await self._handle_response(response)
        return TaskResponse(**data["r"])
    except aiohttp.ClientError as e:
      logger.error(f"Request failed: {e}")
      raise ApiError(status_code=0, detail=f"Request failed: {str(e)}") from None

  async def _get_task(self, task_id: str, query_params: dict[str, Any] | None = None) -> TaskResponse:
    """Retrieves the status and result of a task asynchronously."""
    if not task_id:
      raise ValueError("Task ID cannot be empty.")

    try:
      session = await self._ensure_session()
      url = f"{self.base_url}/task/{task_id}"
      async with session.get(url, params=query_params) as response:
        data = await self._handle_response(response)
        return TaskResponse(**data["r"])
    except aiohttp.ClientError as e:
      logger.error(f"Request failed: {e}")
      raise ApiError(status_code=0, detail=f"Request failed: {str(e)}") from None

  async def _update_task(self, task_id: str, payload: TaskUpdateRequest) -> bool:
    """Updates a running task with user input asynchronously."""
    if not task_id:
      raise ValueError("Task ID cannot be empty.")

    try:
      session = await self._ensure_session()
      async with session.put(f"{self.base_url}/task/{task_id}", json=payload.model_dump()) as response:
        await self._handle_response(response)
        return True
    except aiohttp.ClientError as e:
      logger.error(f"Request failed: {e}")
      raise ApiError(status_code=0, detail=f"Request failed: {str(e)}") from None

  async def _send_task_event(self, task_id: str, event: TaskEvent):
    """Sends an event to a running task asynchronously."""
    if not task_id:
      raise ValueError("Task ID cannot be empty.")

    try:
      session = await self._ensure_session()
      async with session.post(
        f"{self.base_url}/task/{task_id}/event",
        json=event.model_dump(),
      ) as response:
        data = await self._handle_response(response)
        return TaskEventResponse(**data["r"])
    except aiohttp.ClientError as e:
      logger.error(f"Request failed: {e}")
      raise ApiError(status_code=0, detail=f"Request failed: {str(e)}") from None

  async def _delete_task(self, task_id: str):
    """Deletes a task asynchronously."""
    if not task_id:
      raise ValueError("Task ID cannot be empty.")

    try:
      session = await self._ensure_session()
      async with session.delete(f"{self.base_url}/task/{task_id}") as response:
        await self._handle_response(response)
    except aiohttp.ClientError as e:
      logger.error(f"Request failed: {e}")
      raise ApiError(status_code=0, detail=f"Request failed: {str(e)}") from None

  # --- Deprecated Methods ---

  @deprecated("open_session is deprecated, use session instead")
  async def open_session(
    self,
    profile_id: str | None = None,
    session_id: str | None = None,
    live_view: bool = True,
    device: DeviceType = "desktop",
    url: str | None = None,
    proxy_server: str | None = None,
    proxy_username: str | None = None,
    proxy_password: str | None = None,
    extensions: list[str] | None = None,
  ):
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
        extensions: List of extensions to install for the browser session.

    Returns:
        The browser session details, including the live URL.

    Raises:
        ApiException: If the API request fails.
    """
    try:
      session = await self._ensure_session()
      async with session.post(
        f"{self.base_url}/browser/session",
        json=BrowserSessionRequest(
          profile_id=profile_id or session_id,
          live_view=live_view,
          device=device,
          url=url,
          proxy_server=proxy_server,
          proxy_username=proxy_username,
          proxy_password=proxy_password,
          extensions=extensions,
        ).model_dump(),
      ) as response:
        data = await self._handle_response(response)
        return BrowserSessionHandle(browser_session=BrowserSessionResponse(**data["r"]))
    except aiohttp.ClientError as e:
      logger.error(f"Request failed: {e}")
      raise ApiError(status_code=0, detail=f"Request failed: {str(e)}") from None

  @deprecated("close_session is deprecated")
  async def close_session(self, live_id: str):
    """Closes a browser session."""
    try:
      session = await self._ensure_session()
      async with session.delete(f"{self.base_url}/browser/session/{live_id}") as response:
        await self._handle_response(response)
    except aiohttp.ClientError as e:
      logger.error(f"Request failed: {e}")
      raise ApiError(status_code=0, detail=f"Request failed: {str(e)}") from None

  @deprecated("list_sessions is deprecated, use list_profiles instead")
  async def list_sessions(self):
    """Lists all browser profiles for the user."""
    return await self.list_profiles()

  @deprecated("delete_session is deprecated, use delete_profile instead")
  async def delete_session(self, session_id: str):
    """Delete a browser profile."""
    await self.delete_profile(session_id)
