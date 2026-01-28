"""Local proxy server with public tunnel exposure.

This module provides functionality to:
1. Start a local HTTP proxy server with authentication (using pproxy)
2. Expose it publicly via flaredantic tunnels (Cloudflare, Serveo, or Microsoft)
3. Return credentials (url, username, password) for connecting to the proxy

Requirements:
    pip install pproxy flaredantic
"""

import asyncio
import json
import os
import secrets
import signal
import string
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

# Tunnel provider types
TunnelProvider = Literal["cloudflare", "serveo", "microsoft"]

# State file location
PROXY_STATE_FILE = Path.home() / ".smooth" / "proxy.json"


@dataclass
class TunnelConfig:
  """Configuration options for the tunnel."""

  provider: TunnelProvider = "cloudflare"
  port: int = 8888
  timeout: int = 30
  verbose: bool = False
  bin_dir: str | None = None
  ssh_dir: str | None = None
  tcp: bool = False
  tunnel_id: str | None = None
  device_login: bool = False
  username: str | None = None
  password: str | None = None


@dataclass
class ProxyCredentials:
  """Credentials for connecting to the proxy."""

  url: str
  username: str
  password: str
  local_port: int
  pid: int | None = None

  def to_dict(self) -> dict[str, str | int | None]:
    """Convert to dictionary for JSON serialization."""
    return {
      "url": self.url,
      "username": self.username,
      "password": self.password,
      "local_port": self.local_port,
      "pid": self.pid,
    }

  @classmethod
  def from_dict(cls, data: dict[str, str | int | None]) -> "ProxyCredentials":
    """Create from dictionary."""
    return cls(
      url=str(data["url"]),
      username=str(data["username"]),
      password=str(data["password"]),
      local_port=int(data["local_port"]),  # type: ignore
      pid=int(pid) if (pid := data.get("pid")) else None,
    )


@dataclass
class _ProxyState:
  """Internal state for the proxy."""

  credentials: ProxyCredentials | None = None
  proxy_server: object | None = None
  proxy_loop: asyncio.AbstractEventLoop | None = None
  proxy_thread: threading.Thread | None = None
  tunnel: object | None = None
  lock: threading.Lock = field(default_factory=threading.Lock)


class LocalProxy:
  """Local proxy server with public tunnel exposure."""

  def __init__(self, config: TunnelConfig | None = None):
    """Initialize the local proxy."""
    self.config = config or TunnelConfig()
    self._state = _ProxyState()

  def _generate_credentials(self) -> tuple[str, str]:
    """Generate random username and password."""
    chars = string.ascii_letters + string.digits
    username = "user_" + "".join(secrets.choice(chars) for _ in range(8))
    password = "".join(secrets.choice(chars) for _ in range(16))
    return username, password

  def _create_tunnel(self) -> tuple[object, str]:
    """Create and start the tunnel based on config."""
    provider = self.config.provider
    port = self.config.port

    if provider == "cloudflare":
      from flaredantic import FlareConfig, FlareTunnel

      config_kwargs: dict[str, int | bool | str] = {
        "port": port,
        "timeout": self.config.timeout,
        "verbose": self.config.verbose,
      }
      if self.config.bin_dir:
        config_kwargs["bin_dir"] = self.config.bin_dir

      config = FlareConfig(**config_kwargs)  # type: ignore
      tunnel = FlareTunnel(config)  # type: ignore
      tunnel.start()  # type: ignore
      return tunnel, tunnel.tunnel_url  # type: ignore

    elif provider == "serveo":
      from flaredantic import ServeoConfig, ServeoTunnel

      config_kwargs: dict[str, int | bool | str] = {
        "port": port,
        "timeout": self.config.timeout,
        "verbose": self.config.verbose,
        "tcp": self.config.tcp,
      }
      if self.config.ssh_dir:
        config_kwargs["ssh_dir"] = self.config.ssh_dir

      config = ServeoConfig(**config_kwargs)  # type: ignore
      tunnel = ServeoTunnel(config)  # type: ignore
      tunnel.start()  # type: ignore
      return tunnel, tunnel.tunnel_url  # type: ignore

    elif provider == "microsoft":
      from flaredantic import MicrosoftConfig, MicrosoftTunnel

      config_kwargs: dict[str, int | bool | str] = {
        "port": port,
        "timeout": self.config.timeout,
        "verbose": self.config.verbose,
      }
      if self.config.bin_dir:
        config_kwargs["bin_dir"] = self.config.bin_dir
      if self.config.tunnel_id:
        config_kwargs["tunnel_id"] = self.config.tunnel_id
      if self.config.device_login:
        config_kwargs["device_login"] = self.config.device_login

      config = MicrosoftConfig(**config_kwargs)  # type: ignore
      tunnel = MicrosoftTunnel(config)  # type: ignore
      tunnel.start()  # type: ignore
      return tunnel, tunnel.tunnel_url  # type: ignore

    else:
      raise ValueError(f"Unknown tunnel provider: {provider}")

  def start(self) -> ProxyCredentials:
    """Start the local proxy server and expose it via tunnel."""
    with self._state.lock:
      if self._state.credentials is not None:
        return self._state.credentials

      # Use provided credentials or generate random ones
      if self.config.username and self.config.password:
        username, password = self.config.username, self.config.password
      else:
        username, password = self._generate_credentials()

      try:
        import pproxy  # type: ignore

        loop = asyncio.new_event_loop()
        server = pproxy.Server(f"http://127.0.0.1:{self.config.port}/#{username}:{password}")  # type: ignore

        def run_proxy():
          asyncio.set_event_loop(loop)
          handler = loop.run_until_complete(server.start_server({"listen": None}))  # type: ignore
          try:
            loop.run_forever()
          finally:
            handler.close()
            loop.run_until_complete(handler.wait_closed())  # type: ignore

        proxy_thread = threading.Thread(target=run_proxy, daemon=True)
        proxy_thread.start()

        self._state.proxy_server = server
        self._state.proxy_loop = loop
        self._state.proxy_thread = proxy_thread

        tunnel, tunnel_url = self._create_tunnel()
        self._state.tunnel = tunnel

        credentials = ProxyCredentials(
          url=tunnel_url,
          username=username,
          password=password,
          local_port=self.config.port,
          pid=os.getpid(),
        )
        self._state.credentials = credentials

        return credentials

      except Exception as e:
        self._cleanup()
        raise RuntimeError(f"Failed to start proxy: {e}") from e

  def stop(self):
    """Stop the local proxy server and tunnel."""
    with self._state.lock:
      self._cleanup()

  def _cleanup(self):
    """Internal cleanup method."""
    if self._state.tunnel is not None:
      try:
        self._state.tunnel.stop()  # type: ignore
      except Exception:
        pass
      self._state.tunnel = None

    if self._state.proxy_loop is not None:
      try:
        self._state.proxy_loop.call_soon_threadsafe(self._state.proxy_loop.stop)
      except Exception:
        pass
      self._state.proxy_loop = None

    self._state.proxy_server = None
    self._state.proxy_thread = None
    self._state.credentials = None

  @property
  def is_running(self) -> bool:
    """Check if the proxy is currently running."""
    with self._state.lock:
      return self._state.credentials is not None

  @property
  def credentials(self) -> ProxyCredentials | None:
    """Get current credentials if proxy is running."""
    with self._state.lock:
      return self._state.credentials

  def __enter__(self) -> ProxyCredentials:
    """Context manager entry."""
    return self.start()

  def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any):
    """Context manager exit."""
    self.stop()


def save_proxy_state(credentials: ProxyCredentials):
  """Save proxy credentials to state file."""
  PROXY_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
  with open(PROXY_STATE_FILE, "w") as f:
    json.dump(credentials.to_dict(), f)


def load_proxy_state() -> ProxyCredentials | None:
  """Load proxy credentials from state file."""
  if not PROXY_STATE_FILE.exists():
    return None
  try:
    with open(PROXY_STATE_FILE) as f:
      data = json.load(f)
    return ProxyCredentials.from_dict(data)
  except Exception:
    return None


def clear_proxy_state():
  """Clear proxy state file."""
  if PROXY_STATE_FILE.exists():
    PROXY_STATE_FILE.unlink()


def is_proxy_running() -> bool:
  """Check if a proxy is currently running."""
  credentials = load_proxy_state()
  if credentials is None or credentials.pid is None:
    return False

  try:
    os.kill(credentials.pid, 0)
    return True
  except (OSError, ProcessLookupError):
    clear_proxy_state()
    return False


def get_proxy_credentials() -> ProxyCredentials | None:
  """Get proxy credentials if proxy is running."""
  if is_proxy_running():
    return load_proxy_state()
  return None


def run_proxy_server(config: TunnelConfig):
  """Run the proxy server (blocking)."""
  local_proxy = LocalProxy(config)

  def signal_handler(sig: Any, frame: Any):
    print("\nStopping proxy...")
    local_proxy.stop()
    clear_proxy_state()
    sys.exit(0)

  signal.signal(signal.SIGINT, signal_handler)
  signal.signal(signal.SIGTERM, signal_handler)

  print(f"Starting proxy on port {config.port} with {config.provider} tunnel...")

  try:
    creds = local_proxy.start()
    save_proxy_state(creds)

    print("\nProxy is running!")
    print(f"  URL:      {creds.url}")
    print(f"  Username: {creds.username}")
    print(f"  Password: {creds.password}")
    print(f"  PID:      {creds.pid}")
    print("\nThe proxy will be automatically used by 'smooth start-session'.")
    print("Press Ctrl+C to stop.\n")

    signal.pause()

  except Exception as e:
    print(f"Error: {e}")
    clear_proxy_state()
    sys.exit(1)
