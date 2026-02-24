"""Tests for smooth._telemetry."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from smooth._telemetry import (
  NoopBackend,
  Telemetry,
  TelemetryBackend,
  _base_properties,
  _make_event,
)


class TestBaseProperties:
  def test_has_required_keys(self):
    props = _base_properties()
    assert "sdk_version" in props
    assert "python_version" in props
    assert "os" in props
    assert "os_version" in props
    assert "arch" in props

  def test_values_are_strings(self):
    for v in _base_properties().values():
      assert isinstance(v, str)


class TestMakeEvent:
  def test_basic_event(self):
    event = _make_event("sdk.run")
    assert event["event"] == "sdk.run"
    assert "timestamp" in event
    assert "sdk_version" in event["properties"]

  def test_custom_properties(self):
    event = _make_event("sdk.run", properties={"url": "https://example.com"})
    assert event["properties"]["url"] == "https://example.com"

  def test_duration(self):
    event = _make_event("sdk.run", duration_ms=150.5)
    assert event["properties"]["duration_ms"] == 150.5

  def test_error(self):
    event = _make_event("sdk.run", error="boom", error_type="ValueError")
    assert event["properties"]["error"] == "boom"
    assert event["properties"]["error_type"] == "ValueError"

  def test_no_duration_when_not_provided(self):
    event = _make_event("sdk.run")
    assert "duration_ms" not in event["properties"]

  def test_no_error_when_not_provided(self):
    event = _make_event("sdk.run")
    assert "error" not in event["properties"]
    assert "error_type" not in event["properties"]


class RecordingBackend(TelemetryBackend):
  """Test backend that records sent batches."""

  def __init__(self):
    self.batches = []

  async def send_batch(self, events, api_key):
    self.batches.append((list(events), api_key))

  async def shutdown(self):
    pass


class TestTelemetryRecord:
  def test_record_enqueues_event_when_enabled(self, monkeypatch):
    import smooth._telemetry as tel_mod

    monkeypatch.setattr(tel_mod, "_ENABLED", True)

    t = Telemetry()
    t._backend = RecordingBackend()
    t._api_key = "key"

    t.record("test.event", properties={"x": 1})
    assert len(t._queue) == 1
    assert t._queue[0]["event"] == "test.event"
    assert t._queue[0]["properties"]["x"] == 1


class TestTelemetryFlush:
  async def test_flush_drains_queue(self):
    t = Telemetry()
    backend = RecordingBackend()
    t._backend = backend
    t._api_key = "test-key"

    for i in range(5):
      t._queue.append(_make_event(f"event.{i}"))

    await t._flush()
    assert len(t._queue) == 0
    assert len(backend.batches) == 1
    events, api_key = backend.batches[0]
    assert len(events) == 5
    assert api_key == "test-key"

  async def test_flush_does_nothing_when_empty(self):
    t = Telemetry()
    backend = RecordingBackend()
    t._backend = backend
    t._api_key = "test-key"

    await t._flush()
    assert len(backend.batches) == 0

  async def test_flush_does_nothing_without_api_key(self):
    t = Telemetry()
    backend = RecordingBackend()
    t._backend = backend
    t._api_key = ""

    t._queue.append(_make_event("test"))
    await t._flush()
    assert len(backend.batches) == 0
    assert len(t._queue) == 1  # Event stays in queue

  async def test_flush_batches_up_to_threshold(self):
    t = Telemetry()
    backend = RecordingBackend()
    t._backend = backend
    t._api_key = "key"

    for i in range(25):
      t._queue.append(_make_event(f"event.{i}"))

    await t._flush()
    events, _ = backend.batches[0]
    assert len(events) == 10
    assert len(t._queue) == 15


class TestTelemetryDisabled:
  """Verify that _ENABLED=False prevents sending."""

  def test_record_does_not_enqueue_when_disabled(self, monkeypatch):
    import smooth._telemetry as tel_mod

    monkeypatch.setattr(tel_mod, "_ENABLED", False)

    t = Telemetry()
    backend = RecordingBackend()
    t._backend = backend
    t._api_key = "key"

    t.record("should.be.ignored", properties={"x": 1})
    assert len(t._queue) == 0

  def test_init_does_not_start_background_loop_when_disabled(self, monkeypatch):
    import smooth._telemetry as tel_mod

    monkeypatch.setattr(tel_mod, "_ENABLED", False)

    t = Telemetry()
    t.init("some-api-key")
    assert t._started is False
    assert t._thread is None

  def test_disabled_telemetry_uses_noop_backend(self, monkeypatch):
    import smooth._telemetry as tel_mod

    monkeypatch.setattr(tel_mod, "_ENABLED", False)

    t = Telemetry()
    assert isinstance(t._backend, NoopBackend)


class TestTelemetrySingleton:
  def test_get_returns_same_instance(self, monkeypatch):
    monkeypatch.setattr(Telemetry, "_instance", None)
    a = Telemetry.get()
    b = Telemetry.get()
    assert a is b
