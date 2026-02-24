"""Non-blocking telemetry for the Smooth SDK and CLI.

Telemetry is sent to the Smooth API, which forwards events to PostHog server-side.
Disable with SMOOTH_TELEMETRY=off environment variable.
"""

from __future__ import annotations

import asyncio
import atexit
import functools
import os
import platform
import threading
import time as _time
from abc import ABC, abstractmethod
from collections import deque
from datetime import datetime, timezone
from typing import Any, Callable, Sequence

import aiohttp

from ._config import SDK_VERSION

# --- Opt-out ---

_ENABLED = os.getenv("SMOOTH_TELEMETRY", "").lower() != "off"

# --- Constants ---

_FLUSH_INTERVAL = 5.0
_FLUSH_THRESHOLD = 10
_MAX_QUEUE_SIZE = 200
_TELEMETRY_URL = os.getenv("SMOOTH_TELEMETRY_URL", "https://api.smooth.sh/api/v1/telemetry")


# --- Event helpers ---


def _base_properties() -> dict[str, str]:
  return {
    "sdk_version": SDK_VERSION,
    "python_version": platform.python_version(),
    "os": platform.system(),
    "os_version": platform.release(),
    "arch": platform.machine(),
  }


def _make_event(
  event_name: str,
  properties: dict[str, Any] | None = None,
  duration_ms: float | None = None,
  error: str | None = None,
  error_type: str | None = None,
) -> dict[str, Any]:
  props: dict[str, Any] = {**_base_properties()}
  if properties:
    props.update(properties)
  if duration_ms is not None:
    props["duration_ms"] = duration_ms
  if error is not None:
    props["error"] = error
  if error_type is not None:
    props["error_type"] = error_type

  return {
    "event": event_name,
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "properties": props,
  }


# --- Backend abstraction ---


class TelemetryBackend(ABC):
  @abstractmethod
  async def send_batch(self, events: Sequence[dict[str, Any]], api_key: str) -> None: ...

  @abstractmethod
  async def shutdown(self) -> None: ...


class HttpBackend(TelemetryBackend):
  def __init__(self) -> None:
    self._session: aiohttp.ClientSession | None = None

  async def _ensure_session(self) -> aiohttp.ClientSession:
    if self._session is None or self._session.closed:
      self._session = aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=5),
      )
    return self._session

  async def send_batch(self, events: Sequence[dict[str, Any]], api_key: str) -> None:
    try:
      session = await self._ensure_session()
      async with session.post(
        _TELEMETRY_URL,
        json={"events": list(events)},
        headers={"apikey": api_key, "Content-Type": "application/json"},
      ):
        pass
    except Exception:
      pass

  async def shutdown(self) -> None:
    if self._session and not self._session.closed:
      await self._session.close()


class NoopBackend(TelemetryBackend):
  async def send_batch(self, events: Sequence[dict[str, Any]], api_key: str) -> None:
    pass

  async def shutdown(self) -> None:
    pass


# --- Singleton ---


class Telemetry:
  _instance: Telemetry | None = None
  _lock = threading.Lock()

  def __init__(self) -> None:
    self._backend: TelemetryBackend = HttpBackend() if _ENABLED else NoopBackend()
    self._queue: deque[dict[str, Any]] = deque(maxlen=_MAX_QUEUE_SIZE)
    self._api_key: str = ""
    self._loop: asyncio.AbstractEventLoop | None = None
    self._thread: threading.Thread | None = None
    self._started = False

    if _ENABLED:
      atexit.register(self._shutdown_sync)

  @classmethod
  def get(cls) -> Telemetry:
    if cls._instance is None:
      with cls._lock:
        if cls._instance is None:
          cls._instance = cls()
    return cls._instance

  def init(self, api_key: str) -> None:
    """Set the API key and start the background flush loop."""
    if not _ENABLED:
      return
    self._api_key = api_key
    if not self._started:
      self._start_background_loop()

  def set_backend(self, backend: TelemetryBackend) -> None:
    self._backend = backend

  def record(
    self,
    event_name: str,
    properties: dict[str, Any] | None = None,
    duration_ms: float | None = None,
    error: str | None = None,
    error_type: str | None = None,
  ) -> None:
    if not _ENABLED:
      return
    try:
      event = _make_event(event_name, properties, duration_ms, error, error_type)
      self._queue.append(event)
      # Flush immediately if we hit the threshold
      if len(self._queue) >= _FLUSH_THRESHOLD and self._loop and self._started:
        self._loop.call_soon_threadsafe(lambda: asyncio.ensure_future(self._flush()))
    except Exception:
      pass

  def _start_background_loop(self) -> None:
    if self._started:
      return
    self._loop = asyncio.new_event_loop()
    self._thread = threading.Thread(target=self._run_loop, daemon=True, name="smooth-telemetry")
    self._thread.start()
    self._started = True

  def _run_loop(self) -> None:
    asyncio.set_event_loop(self._loop)
    assert self._loop is not None
    self._loop.run_until_complete(self._flush_loop())

  async def _flush_loop(self) -> None:
    while True:
      await asyncio.sleep(_FLUSH_INTERVAL)
      await self._flush()

  async def _flush(self) -> None:
    if not self._queue or not self._api_key:
      return
    batch: list[dict[str, Any]] = []
    while self._queue and len(batch) < _FLUSH_THRESHOLD:
      batch.append(self._queue.popleft())
    if batch:
      await self._backend.send_batch(batch, self._api_key)

  def _shutdown_sync(self) -> None:
    if not _ENABLED or not self._loop:
      return
    try:
      future = asyncio.run_coroutine_threadsafe(self._flush_and_shutdown(), self._loop)
      future.result(timeout=2.0)
    except Exception:
      pass

  async def _flush_and_shutdown(self) -> None:
    # Flush all remaining events
    while self._queue:
      await self._flush()
    await self._backend.shutdown()


# --- Decorators ---


def track(event_name: str, properties_fn: Callable[[tuple[Any, ...], dict[str, Any]], dict[str, Any] | None] | None = None):
  """Decorator that records a telemetry event wrapping a function call.

  Works for both sync and async functions. Records duration and errors.
  """

  def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
    if asyncio.iscoroutinefunction(fn):

      @functools.wraps(fn)
      async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
        props = None
        try:
          props = properties_fn(args, kwargs) if properties_fn else None
        except Exception:
          pass
        start = _time.monotonic()
        try:
          result = await fn(*args, **kwargs)
          duration = (_time.monotonic() - start) * 1000
          Telemetry.get().record(event_name, properties=props, duration_ms=duration)
          return result
        except Exception as e:
          duration = (_time.monotonic() - start) * 1000
          Telemetry.get().record(
            event_name,
            properties=props,
            duration_ms=duration,
            error=str(e),
            error_type=type(e).__name__,
          )
          raise

      return async_wrapper
    else:

      @functools.wraps(fn)
      def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
        props = None
        try:
          props = properties_fn(args, kwargs) if properties_fn else None
        except Exception:
          pass
        start = _time.monotonic()
        try:
          result = fn(*args, **kwargs)
          duration = (_time.monotonic() - start) * 1000
          Telemetry.get().record(event_name, properties=props, duration_ms=duration)
          return result
        except Exception as e:
          duration = (_time.monotonic() - start) * 1000
          Telemetry.get().record(
            event_name,
            properties=props,
            duration_ms=duration,
            error=str(e),
            error_type=type(e).__name__,
          )
          raise

      return sync_wrapper

  return decorator
