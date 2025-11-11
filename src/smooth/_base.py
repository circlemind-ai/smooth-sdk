# pyright: reportPrivateUsage=false
"""Smooth python SDK types and models."""

import io
import logging
import os
import warnings
from typing import Any, Literal, NotRequired, TypedDict

import httpx
import requests
from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

# Configure logging
logger = logging.getLogger("smooth")


BASE_URL = "https://api.smooth.sh/api/"

# --- Models ---


class Certificate(TypedDict):
  """Client certificate for accessing secure websites.

  Attributes:
      file: p12 file object to be uploaded (e.g., open("cert.p12", "rb")).
      password: Password to decrypt the certificate file. Optional.
  """

  file: str | io.IOBase  # Required - base64 string or binary IO
  password: NotRequired[str]  # Optional
  filters: NotRequired[
    list[str]
  ]  # Optional - TODO: Reserved for future use to specify URL patterns where the certificate should be applied.


class ToolSignature(BaseModel):
  """Tool signature model."""

  name: str = Field(description="The name of the tool.")
  description: str = Field(description="The description of the tool.")
  inputs: dict[str, Any] = Field(description="The input schema of the tool.")
  output: str = Field(description="The output schema of the tool.")


class ToolCall(BaseModel):
  """Tool call model."""

  model_config = ConfigDict(extra="allow")  # we use the same field for request and response

  # Request params
  name: str | None = Field(default=None, description="The name of the tool being called.")
  input: str | None = Field(default=None, description="The input provided to the tool (json encoded).")

  # Response params
  code: str | None = Field(default=None, description="The tool call returned HTTP status code.")
  output: str | None = Field(default=None, description="The output produced by the tool (json encoded).")


class ToolCallResponse(BaseModel):
  """Tool call response model."""

  model_config = ConfigDict(extra="allow")  # we use the same field for request and response

  id: str = Field(description="The ID of the tool call.")
  code: int = Field(description="The HTTP status code of the tool call.")
  output: str = Field(description="The output produced by the tool (json encoded).")


class TaskResponse(BaseModel):
  """Task response model."""

  model_config = ConfigDict(extra="allow")

  id: str = Field(description="The ID of the task.")
  status: Literal["waiting", "running", "done", "failed", "cancelled"] = Field(description="The status of the task.")
  output: Any | None = Field(default=None, description="The output of the task.")
  credits_used: int | None = Field(default=None, description="The amount of credits used to perform the task.")
  device: Literal["desktop", "mobile"] | None = Field(default=None, description="The device type used for the task.")
  live_url: str | None = Field(
    default=None,
    description="The URL to view and interact with the task execution.",
  )
  recording_url: str | None = Field(default=None, description="The URL to view the task recording.")
  downloads_url: str | None = Field(
    default=None,
    description="The URL of the archive containing the downloaded files.",
  )
  created_at: int | None = Field(default=None, description="The timestamp when the task was created.")
  tool_calls: dict[str, ToolCall] | None = Field(default=None, description="TODO")


class TaskRequest(BaseModel):
  """Run task request model."""

  model_config = ConfigDict(extra="allow")

  task: str = Field(description="The task to run.")
  response_model: dict[str, Any] | None = Field(
    default=None,
    description="If provided, the JSON schema describing the desired output structure. Default is None",
  )
  url: str | None = Field(
    default=None,
    description="The starting URL for the task. If not provided, the agent will infer it from the task.",
  )
  metadata: dict[str, str | int | float | bool] | None = Field(
    default=None,
    description="A dictionary containing variables or parameters that will be passed to the agent.",
  )
  files: list[str] | None = Field(default=None, description="A list of file ids to pass to the agent.")
  agent: Literal["smooth", "smooth-lite"] = Field(default="smooth", description="The agent to use for the task.")
  max_steps: int = Field(
    default=32,
    ge=2,
    le=128,
    description="Maximum number of steps the agent can take (min 2, max 128).",
  )
  device: Literal["desktop", "mobile"] = Field(default="desktop", description="Device type for the task. Default is desktop.")
  allowed_urls: list[str] | None = Field(
    default=None,
    description=(
      "List of allowed URL patterns using wildcard syntax (e.g., https://*example.com/*). If None, all URLs are allowed."
    ),
  )
  enable_recording: bool = Field(
    default=True,
    description="Enable video recording of the task execution. Default is True",
  )
  profile_id: str | None = Field(
    default=None,
    description=("Browser profile ID to use. Each profile maintains its own state, such as cookies and login credentials."),
  )
  profile_read_only: bool = Field(
    default=False,
    description=(
      "If true, the profile specified by `profile_id` will be loaded in read-only mode. "
      "Changes made during the task will not be saved back to the profile."
    ),
  )
  stealth_mode: bool = Field(default=False, description="Run the browser in stealth mode.")
  proxy_server: str | None = Field(
    default=None,
    description=("Proxy server url to route browser traffic through."),
  )
  proxy_username: str | None = Field(default=None, description="Proxy server username.")
  proxy_password: str | None = Field(default=None, description="Proxy server password.")
  certificates: list[dict[str, Any]] | None = Field(
    default=None,
    description=(
      "List of client certificates to use when accessing secure websites. "
      "Each certificate is a dictionary with the following fields:\n"
      " - `file`: p12 file object to be uploaded (e.g., open('cert.p12', 'rb')).\n"
      " - `password` (optional): Password to decrypt the certificate file."
    ),
  )
  use_adblock: bool | None = Field(
    default=True,
    description="Enable adblock for the browser session. Default is True.",
  )
  additional_tools: dict[str, dict[str, Any] | None] | None = Field(
    default=None, description="Additional tools to enable for the task."
  )
  custom_tools: list[ToolSignature] | None = Field(
    default=None, description="Custom tools to register for the task."
  )
  experimental_features: dict[str, Any] | None = Field(
    default=None, description="Experimental features to enable for the task."
  )
  extensions: list[str] | None = Field(default=None, description="List of extensions to install for the task.")

  @model_validator(mode="before")
  @classmethod
  def _handle_deprecated_session_id(cls, data: Any) -> Any:
    if isinstance(data, dict) and "session_id" in data and "profile_id" not in data:
      warnings.warn(
        "'session_id' is deprecated, use 'profile_id' instead",
        DeprecationWarning,
        stacklevel=2,
      )
      data["profile_id"] = data.pop("session_id")
    return data

  @computed_field(return_type=str | None)
  @property
  def session_id(self):
    """(Deprecated) Returns the session ID."""
    warnings.warn(
      "'session_id' is deprecated, use 'profile_id' instead",
      DeprecationWarning,
      stacklevel=2,
    )
    return self.profile_id

  @session_id.setter
  def session_id(self, value: str | None):
    """(Deprecated) Sets the session ID."""
    warnings.warn(
      "'session_id' is deprecated, use 'profile_id' instead",
      DeprecationWarning,
      stacklevel=2,
    )
    self.profile_id = value

  def model_dump(self, **kwargs: Any) -> dict[str, Any]:
    """Dump model to dict, including deprecated session_id for retrocompatibility."""
    data = super().model_dump(**kwargs)
    # Add deprecated session_id field for retrocompatibility
    if "profile_id" in data:
      data["session_id"] = data["profile_id"]
    return data


class TaskUpdateRequest(BaseModel):
  """Update task request model."""

  model_config = ConfigDict(extra="allow")

  tool_response: ToolCallResponse | None = Field(default=None, description="The tool response to the agent query.")


class BrowserSessionRequest(BaseModel):
  """Request model for creating a browser session."""

  model_config = ConfigDict(extra="allow")

  profile_id: str | None = Field(
    default=None,
    description=("The profile ID to use for the browser session. If None, a new profile will be created."),
  )
  live_view: bool | None = Field(
    default=True,
    description="Request a live URL to interact with the browser session.",
  )
  device: Literal["desktop", "mobile"] | None = Field(default="desktop", description="The device type to use.")
  url: str | None = Field(default=None, description="The URL to open in the browser session.")
  proxy_server: str | None = Field(
    default=None,
    description=("Proxy server address to route browser traffic through."),
  )
  proxy_username: str | None = Field(default=None, description="Proxy server username.")
  proxy_password: str | None = Field(default=None, description="Proxy server password.")

  @model_validator(mode="before")
  @classmethod
  def _handle_deprecated_session_id(cls, data: Any) -> Any:
    if isinstance(data, dict) and "session_id" in data and "profile_id" not in data:
      warnings.warn(
        "'session_id' is deprecated, use 'profile_id' instead",
        DeprecationWarning,
        stacklevel=2,
      )
      data["profile_id"] = data.pop("session_id")
    return data

  @computed_field(return_type=str | None)
  @property
  def session_id(self):
    """(Deprecated) Returns the session ID."""
    warnings.warn(
      "'session_id' is deprecated, use 'profile_id' instead",
      DeprecationWarning,
      stacklevel=2,
    )
    return self.profile_id

  @session_id.setter
  def session_id(self, value: str | None):
    """(Deprecated) Sets the session ID."""
    warnings.warn(
      "'session_id' is deprecated, use 'profile_id' instead",
      DeprecationWarning,
      stacklevel=2,
    )
    self.profile_id = value

  def model_dump(self, **kwargs: Any) -> dict[str, Any]:
    """Dump model to dict, including deprecated session_id for retrocompatibility."""
    data = super().model_dump(**kwargs)
    # Add deprecated session_id field for retrocompatibility
    if "profile_id" in data:
      data["session_id"] = data["profile_id"]
    return data


class BrowserSessionResponse(BaseModel):
  """Browser session response model."""

  model_config = ConfigDict(extra="allow")

  profile_id: str = Field(description="The ID of the browser profile associated with the opened browser instance.")
  live_id: str | None = Field(default=None, description="The ID of the live browser session.")
  live_url: str | None = Field(default=None, description="The live URL to interact with the browser session.")

  @model_validator(mode="before")
  @classmethod
  def _handle_deprecated_session_id(cls, data: Any) -> Any:
    if isinstance(data, dict) and "session_id" in data and "profile_id" not in data:
      warnings.warn(
        "'session_id' is deprecated, use 'profile_id' instead",
        DeprecationWarning,
        stacklevel=2,
      )
      data["profile_id"] = data.pop("session_id")
    return data

  @computed_field(return_type=str | None)
  @property
  def session_id(self):
    """(Deprecated) Returns the session ID."""
    warnings.warn(
      "'session_id' is deprecated, use 'profile_id' instead",
      DeprecationWarning,
      stacklevel=2,
    )
    return self.profile_id

  @session_id.setter
  def session_id(self, value: str):
    """(Deprecated) Sets the session ID."""
    warnings.warn(
      "'session_id' is deprecated, use 'profile_id' instead",
      DeprecationWarning,
      stacklevel=2,
    )
    self.profile_id = value


class BrowserProfilesResponse(BaseModel):
  """Response model for listing browser profiles."""

  model_config = ConfigDict(extra="allow")

  profile_ids: list[str] = Field(description="The IDs of the browser profiles.")

  @model_validator(mode="before")
  @classmethod
  def _handle_deprecated_session_ids(cls, data: Any) -> Any:
    if isinstance(data, dict) and "session_ids" in data and "profile_ids" not in data:
      warnings.warn(
        "'session_ids' is deprecated, use 'profile_ids' instead",
        DeprecationWarning,
        stacklevel=2,
      )
      data["profile_ids"] = data.pop("session_ids")
    return data

  @computed_field(return_type=list[str])
  @property
  def session_ids(self):
    """(Deprecated) Returns the session IDs."""
    warnings.warn(
      "'session_ids' is deprecated, use 'profile_ids' instead",
      DeprecationWarning,
      stacklevel=2,
    )
    return self.profile_ids

  @session_ids.setter
  def session_ids(self, value: list[str]):
    """(Deprecated) Sets the session IDs."""
    warnings.warn(
      "'session_ids' is deprecated, use 'profile_ids' instead",
      DeprecationWarning,
      stacklevel=2,
    )
    self.profile_ids = value

  def model_dump(self, **kwargs: Any) -> dict[str, Any]:
    """Dump model to dict, including deprecated session_ids for retrocompatibility."""
    data = super().model_dump(**kwargs)
    # Add deprecated session_ids field for retrocompatibility
    if "profile_ids" in data:
      data["session_ids"] = data["profile_ids"]
    return data


class BrowserSessionsResponse(BrowserProfilesResponse):
  """Response model for listing browser profiles."""

  pass


class UploadFileResponse(BaseModel):
  """Response model for uploading a file."""

  model_config = ConfigDict(extra="allow")

  id: str = Field(description="The ID assigned to the uploaded file.")


class UploadExtensionResponse(BaseModel):
  """Response model for uploading an extension."""

  model_config = ConfigDict(extra="allow")

  id: str = Field(description="The uploaded extension ID.")


class Extension(BaseModel):
  """Extension model."""

  model_config = ConfigDict(extra="allow")

  id: str = Field(description="The ID of the extension.")
  file_name: str = Field(description="The name of the extension.")
  creation_time: int = Field(description="The creation timestamp.")


class ListExtensionsResponse(BaseModel):
  """Response model for listing extensions."""

  model_config = ConfigDict(extra="allow")

  extensions: list[Extension] = Field(description="The list of extensions.")


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


class ToolCallError(Exception):
  """Custom exception for tool call errors."""

  pass


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
      "User-Agent": "smooth-python-sdk/0.2.5",
    }

  def _handle_response(self, response: requests.Response | httpx.Response) -> dict[str, Any]:
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

  def _submit_task(self, payload: TaskRequest) -> TaskResponse:
    raise NotImplementedError

  def _get_task(self, task_id: str, query_params: dict[str, Any] | None = None) -> TaskResponse:
    raise NotImplementedError

  def _delete_task(self, task_id: str) -> None:
    raise NotImplementedError

  def _update_task(self, task_id: str, payload: TaskUpdateRequest) -> bool:
    raise NotImplementedError


class BaseTaskHandle:
  """A handle to a running task."""

  def __init__(self, task_id: str):
    """Initializes the task handle."""
    self._task_response: TaskResponse | None = None

    self._id = task_id

  def id(self):
    """Returns the task ID."""
    return self._id

  def stop(self) -> None:
    raise NotImplementedError

  def update(self, payload: TaskUpdateRequest) -> bool:
    raise NotImplementedError

  def result(self, timeout: int | None = None, poll_interval: float = 1) -> TaskResponse:
    raise NotImplementedError

  def live_url(self, interactive: bool = False, embed: bool = False, timeout: int | None = None) -> str:
    raise NotImplementedError

  def recording_url(self, timeout: int | None = None) -> str:
    raise NotImplementedError

  def downloads_url(self, timeout: int | None = None) -> str:
    raise NotImplementedError


class BaseAsyncTaskHandle(BaseTaskHandle):
  """A handle to a running task."""

  def __init__(self, task_id: str):
    """Initializes the task handle."""
    super().__init__(task_id)

  async def stop(self) -> None:
    raise NotImplementedError

  async def update(self, payload: TaskUpdateRequest) -> bool:
    raise NotImplementedError

  async def result(self, timeout: int | None = None, poll_interval: float = 1) -> TaskResponse:
    raise NotImplementedError

  async def live_url(self, interactive: bool = False, embed: bool = False, timeout: int | None = None) -> str:
    raise NotImplementedError

  async def recording_url(self, timeout: int | None = None) -> str:
    raise NotImplementedError

  async def downloads_url(self, timeout: int | None = None) -> str:
    raise NotImplementedError
