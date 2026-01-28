# pyright: reportPrivateUsage=false
"""Smooth python SDK."""

from ._client import ProxyConfig, SmoothAsyncClient, SmoothClient
from ._exceptions import ApiError, BadRequestError, TimeoutError, ToolCallError
from ._interface import (
  AsyncSessionHandle,
  AsyncTaskHandle,
  BrowserSessionHandle,
  SessionHandle,
  TaskHandle,
)
from ._tools import (
  AsyncSmoothTool,
  SmoothTool,
)

# Export public API
__all__ = [
  "SmoothClient",
  "SmoothAsyncClient",
  "ProxyConfig",
  "SessionHandle",
  "AsyncSessionHandle",
  "AsyncSmoothTool",
  "SmoothTool",
  "ApiError",
  "BadRequestError",
  "TimeoutError",
  "ToolCallError",
  # Deprecated
  "TaskHandle",
  "AsyncTaskHandle",
  "BrowserSessionHandle",
]
