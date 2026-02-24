"""Tests for smooth._client."""

import os
from unittest.mock import AsyncMock, patch

import aiohttp
import pytest
from aioresponses import aioresponses

from smooth._client import BaseClient, SmoothAsyncClient, SmoothClient, _get_proxy_url
from smooth._exceptions import ApiError

FAKE_KEY = "cmzr-test-key-0123456789abcdef"


# --- _get_proxy_url ---


class TestGetProxyUrl:
  def test_parses_base64_b_param(self):
    import base64

    raw_url = "https://browser-live.example.com/view?extra=1"
    encoded = base64.urlsafe_b64encode(raw_url.encode()).decode().rstrip("=")
    live_url = f"https://live.example.com/session?b={encoded}"
    result = _get_proxy_url(live_url)
    assert "browser-proxy.example.com" in result
    assert "browser-live" not in result

  def test_raises_on_missing_b_param(self):
    with pytest.raises(RuntimeError, match="No proxy URL provided"):
      _get_proxy_url("https://live.example.com/session?other=1")

  def test_strips_query_and_trailing_slash(self):
    import base64

    raw_url = "https://browser-live.foo.com/path/?q=1"
    encoded = base64.urlsafe_b64encode(raw_url.encode()).decode().rstrip("=")
    result = _get_proxy_url(f"https://x.com/?b={encoded}")
    assert not result.endswith("/")
    assert "?" not in result


# --- BaseClient.__init__ ---


class TestBaseClientInit:
  def test_requires_api_key(self):
    with patch.dict(os.environ, {}, clear=True):
      os.environ.pop("CIRCLEMIND_API_KEY", None)
      with pytest.raises(ValueError, match="API key is required"):
        BaseClient(api_key=None)

  def test_uses_env_var_when_no_key_provided(self):
    with patch.dict(os.environ, {"CIRCLEMIND_API_KEY": FAKE_KEY}):
      client = BaseClient()
      assert client.api_key == FAKE_KEY

  def test_explicit_key_overrides_env(self):
    with patch.dict(os.environ, {"CIRCLEMIND_API_KEY": "env-key"}):
      client = BaseClient(api_key=FAKE_KEY)
      assert client.api_key == FAKE_KEY

  def test_constructs_base_url_with_version(self):
    client = BaseClient(api_key=FAKE_KEY, base_url="https://api.test.com/", api_version="v2")
    assert client.base_url == "https://api.test.com/v2"

  def test_strips_trailing_slash_from_base_url(self):
    client = BaseClient(api_key=FAKE_KEY, base_url="https://api.test.com///")
    assert client.base_url == "https://api.test.com/v1"

  def test_sets_headers(self):
    client = BaseClient(api_key=FAKE_KEY)
    assert client.headers["apikey"] == FAKE_KEY
    assert "smooth-python-sdk" in client.headers["User-Agent"]

  def test_raises_on_empty_base_url(self):
    with pytest.raises(ValueError, match="Base URL cannot be empty"):
      BaseClient(api_key=FAKE_KEY, base_url="")


# --- SmoothAsyncClient ---


class TestSmoothAsyncClient:
  @pytest.fixture()
  def client(self):
    return SmoothAsyncClient(api_key=FAKE_KEY, base_url="https://api.test.com/api/", timeout=5, retries=0)

  async def test_ensure_session_creates_session(self, client):
    assert client._client is None
    session = await client._ensure_session()
    assert session is not None
    assert client._client is not None
    await client.close()

  async def test_ensure_session_reuses_existing(self, client):
    s1 = await client._ensure_session()
    s2 = await client._ensure_session()
    assert s1 is s2
    await client.close()

  async def test_context_manager(self):
    async with SmoothAsyncClient(api_key=FAKE_KEY, retries=0) as client:
      assert client._client is not None
    assert client._client is None

  async def test_retry_client_when_retries_positive(self):
    async with SmoothAsyncClient(api_key=FAKE_KEY, retries=2) as client:
      assert client._retry_client is not None

  async def test_no_retry_client_when_retries_zero(self):
    async with SmoothAsyncClient(api_key=FAKE_KEY, retries=0) as client:
      assert client._retry_client is None


# --- _handle_response ---


class TestHandleResponse:
  @pytest.fixture()
  def client(self):
    return SmoothAsyncClient(api_key=FAKE_KEY, retries=0)

  async def test_success_json(self, client):
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value={"r": {"id": "t-1"}})
    result = await client._handle_response(mock_resp)
    assert result == {"r": {"id": "t-1"}}

  async def test_success_invalid_json(self, client):
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(side_effect=ValueError("bad json"))
    with pytest.raises(ApiError) as exc_info:
      await client._handle_response(mock_resp)
    assert exc_info.value.status_code == 200
    assert "Invalid JSON" in exc_info.value.detail

  async def test_error_with_json_detail(self, client):
    mock_resp = AsyncMock()
    mock_resp.status = 422
    mock_resp.json = AsyncMock(return_value={"detail": "Validation failed"})
    mock_resp.text = AsyncMock(return_value="Validation failed")
    with pytest.raises(ApiError) as exc_info:
      await client._handle_response(mock_resp)
    assert exc_info.value.status_code == 422
    assert "Validation failed" in exc_info.value.detail

  async def test_error_with_non_json_body(self, client):
    mock_resp = AsyncMock()
    mock_resp.status = 500
    mock_resp.json = AsyncMock(side_effect=ValueError("not json"))
    mock_resp.text = AsyncMock(return_value="Internal Server Error")
    with pytest.raises(ApiError) as exc_info:
      await client._handle_response(mock_resp)
    assert exc_info.value.status_code == 500
    assert "Internal Server Error" in exc_info.value.detail

  async def test_error_empty_text(self, client):
    mock_resp = AsyncMock()
    mock_resp.status = 502
    mock_resp.json = AsyncMock(side_effect=ValueError())
    mock_resp.text = AsyncMock(return_value="")
    with pytest.raises(ApiError) as exc_info:
      await client._handle_response(mock_resp)
    assert "HTTP 502" in exc_info.value.detail

  async def test_error_json_without_detail_key(self, client):
    """When error response JSON has no 'detail' key, falls back to response.text()."""
    mock_resp = AsyncMock()
    mock_resp.status = 422
    mock_resp.json = AsyncMock(return_value={"error": "some_error", "code": "INVALID"})
    mock_resp.text = AsyncMock(return_value="Unprocessable Entity")
    with pytest.raises(ApiError) as exc_info:
      await client._handle_response(mock_resp)
    assert exc_info.value.detail == "Unprocessable Entity"
    assert exc_info.value.response_data == {"error": "some_error", "code": "INVALID"}


# --- API method tests with aioresponses ---


class TestAsyncClientApiMethods:
  BASE = "https://api.test.com/api/v1"

  @pytest.fixture()
  def client(self):
    return SmoothAsyncClient(api_key=FAKE_KEY, base_url="https://api.test.com/api/", retries=0)

  async def test_submit_task(self, client):
    from smooth.models import TaskRequest

    with aioresponses() as m:
      m.post(f"{self.BASE}/task", payload={"r": {"id": "t-1", "status": "running"}})
      async with client:
        payload = TaskRequest(task="do something")
        resp = await client._submit_task(payload)
        assert resp.id == "t-1"
        assert resp.status == "running"

  async def test_get_task(self, client):
    with aioresponses() as m:
      m.get(f"{self.BASE}/task/t-1", payload={"r": {"id": "t-1", "status": "done", "output": "result"}})
      async with client:
        resp = await client._get_task("t-1")
        assert resp.id == "t-1"
        assert resp.status == "done"

  async def test_get_task_empty_id_raises(self, client):
    with pytest.raises(ValueError, match="Task ID cannot be empty"):
      await client._get_task("")

  async def test_get_task_with_query_params(self, client):
    with aioresponses() as m:
      m.get(f"{self.BASE}/task/t-1?event_t=100", payload={"r": {"id": "t-1", "status": "running"}})
      async with client:
        resp = await client._get_task("t-1", query_params={"event_t": 100})
        assert resp.id == "t-1"

  async def test_delete_task(self, client):
    with aioresponses() as m:
      m.delete(f"{self.BASE}/task/t-1", payload={"r": {}})
      async with client:
        await client._delete_task("t-1")  # Should not raise

  async def test_delete_task_empty_id_raises(self, client):
    with pytest.raises(ValueError, match="Task ID cannot be empty"):
      await client._delete_task("")

  async def test_send_task_event(self, client):
    from smooth.models import TaskEvent

    with aioresponses() as m:
      m.post(f"{self.BASE}/task/t-1/event", payload={"r": {"id": "e-1"}})
      async with client:
        event = TaskEvent(name="tool_call", payload={"name": "click"})
        resp = await client._send_task_event("t-1", event)
        assert resp.id == "e-1"

  async def test_create_profile(self, client):
    with aioresponses() as m:
      m.post(f"{self.BASE}/profile", payload={"r": {"id": "p-1"}})
      async with client:
        resp = await client.create_profile(profile_id="p-1")
        assert resp.id == "p-1"

  async def test_list_profiles(self, client):
    with aioresponses() as m:
      m.get(f"{self.BASE}/profile", payload={"r": [{"id": "p-1"}, {"id": "p-2"}]})
      async with client:
        profiles = await client.list_profiles()
        assert len(profiles) == 2
        assert profiles[0].id == "p-1"

  async def test_delete_profile(self, client):
    with aioresponses() as m:
      m.delete(f"{self.BASE}/profile/p-1", payload={"r": {}})
      async with client:
        await client.delete_profile("p-1")

  async def test_upload_file(self, client):
    import io

    with aioresponses() as m:
      m.post(f"{self.BASE}/file", payload={"r": {"id": "f-1"}})
      async with client:
        f = io.BytesIO(b"file-content")
        f.name = "test.txt"
        resp = await client.upload_file(f)
        assert resp.id == "f-1"

  async def test_upload_file_no_name_raises(self, client):
    import io

    async with client:
      f = io.BytesIO(b"data")
      # BytesIO has no name attribute
      with pytest.raises(ValueError, match="File name must be provided"):
        await client.upload_file(f)

  async def test_delete_file(self, client):
    with aioresponses() as m:
      m.delete(f"{self.BASE}/file/f-1", payload={"r": {}})
      async with client:
        await client.delete_file("f-1")

  async def test_upload_extension(self, client):
    import io

    with aioresponses() as m:
      m.post(f"{self.BASE}/extension", payload={"r": {"id": "ext-1"}})
      async with client:
        f = io.BytesIO(b"ext-data")
        f.name = "ext.zip"
        resp = await client.upload_extension(f)
        assert resp.id == "ext-1"

  async def test_list_extensions(self, client):
    with aioresponses() as m:
      m.get(
        f"{self.BASE}/extension",
        payload={"r": [{"id": "ext-1", "file_name": "a.zip", "creation_time": 100}]},
      )
      async with client:
        exts = await client.list_extensions()
        assert len(exts) == 1
        assert exts[0].id == "ext-1"

  async def test_delete_extension(self, client):
    with aioresponses() as m:
      m.delete(f"{self.BASE}/extension/ext-1", payload={"r": {}})
      async with client:
        await client.delete_extension("ext-1")

  async def test_api_error_propagated(self, client):
    with aioresponses() as m:
      m.get(f"{self.BASE}/task/t-1", status=404, payload={"detail": "Not found"})
      async with client:
        with pytest.raises(ApiError) as exc_info:
          await client._get_task("t-1")
        assert exc_info.value.status_code == 404

  async def test_client_error_wrapped_as_api_error(self, client):
    """aiohttp.ClientError during request is caught and re-raised as ApiError with status_code=0."""
    with aioresponses() as m:
      m.post(f"{self.BASE}/profile", exception=aiohttp.ServerDisconnectedError("Connection refused"))
      async with client:
        with pytest.raises(ApiError) as exc_info:
          await client.create_profile()
        assert exc_info.value.status_code == 0
        assert "Connection refused" in exc_info.value.detail


# --- SmoothClient (sync wrapper) ---


class TestSmoothClientSync:
  @pytest.fixture()
  def client(self, mock_env_api_key):
    c = SmoothClient()
    yield c
    # Cleanup background event loop thread
    if c._loop.is_running():
      c._loop.call_soon_threadsafe(c._loop.stop)

  def test_sync_client_wraps_async(self, client):
    assert client._async_client is not None
    assert client._loop.is_running()

  def test_tool_decorator_rejects_async(self, client):
    with pytest.raises(TypeError, match="cannot wrap async function"):

      @client.tool(name="t", description="d", inputs={}, output="o")
      async def my_async_tool():
        pass

  def test_tool_decorator_accepts_sync(self, client):
    @client.tool(name="my_tool", description="does stuff", inputs={"x": "int"}, output="result")
    def my_sync_tool(x):
      return x

    assert my_sync_tool.name == "my_tool"


# --- SmoothAsyncClient tool decorator ---


class TestAsyncClientToolDecorator:
  def test_rejects_sync_function(self):
    client = SmoothAsyncClient(api_key=FAKE_KEY)

    with pytest.raises(TypeError, match="cannot wrap non-async function"):

      @client.tool(name="t", description="d", inputs={}, output="o")
      def my_sync_fn():
        pass

  def test_accepts_async_function(self):
    client = SmoothAsyncClient(api_key=FAKE_KEY)

    @client.tool(name="my_tool", description="does stuff", inputs={"x": "int"}, output="result")
    async def my_async_fn(x):
      return x

    assert my_async_fn.name == "my_tool"
