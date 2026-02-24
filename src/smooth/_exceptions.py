import builtins
from typing import Any


class ApiError(Exception):
  """Custom exception for API errors."""

  def __init__(self, status_code: int, detail: str, response_data: dict[str, Any] | None = None):
    """Initializes the API error."""
    self.status_code = status_code
    self.detail = detail
    self.response_data = response_data
    super().__init__(f"API Error {status_code}: {detail}")


class BadRequestError(Exception):
  """Custom exception for bad requests."""

  pass


class TimeoutError(builtins.TimeoutError):
  """Custom exception for task timeouts."""

  pass


class ToolCallError(Exception):
  """Custom exception for tool call errors."""

  pass
