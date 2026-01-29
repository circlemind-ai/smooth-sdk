"""FRP-based proxy tunnel for exposing local SOCKS5 proxy.

This module provides functionality to:
1. Download and install the FRP client binary (frpc)
2. Start a SOCKS5 proxy tunnel to a remote FRP server
3. Manage proxy lifecycle per session

The proxy connects to a remote FRP server and exposes a local SOCKS5 proxy
that can be used by the browser session.
"""

import platform
import shutil
import subprocess
import tarfile
import tempfile
import threading
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# FRP version to use
FRP_VERSION = "0.66.0"

# Directory to store FRP binaries and configs
FRP_DIR = Path.home() / ".smooth" / "frp"


@dataclass
class ProxyConfig:
  """Configuration for the FRP proxy tunnel."""

  server_url: str
  token: str
  remote_port: int = 1080
  session_id: str = "default"


@dataclass
class _ProxyState:
  """Internal state for a proxy instance."""

  process: subprocess.Popen[bytes] | None = None
  config_file: Path | None = None
  lock: threading.Lock = field(default_factory=threading.Lock)


class FRPProxy:
  """FRP-based proxy tunnel manager."""

  def __init__(self, config: ProxyConfig):
    """Initialize the FRP proxy.

    Args:
        config: Proxy configuration with server details and token.
    """
    self.config = config
    self._state = _ProxyState()
    self._bin_path: Path | None = None

  @staticmethod
  def _get_platform_info() -> tuple[str, str, str]:
    """Get platform-specific information for FRP download.

    Returns:
        Tuple of (os_name, arch, extension).

    Raises:
        RuntimeError: If the platform is not supported.
    """
    system = platform.system().lower()
    machine = platform.machine().lower()

    # Map OS
    if system == "darwin":
      os_name = "darwin"
    elif system == "windows":
      os_name = "windows"
    else:
      os_name = "linux"

    # Map architecture
    if machine in ["x86_64", "amd64"]:
      arch = "amd64"
    elif machine in ["aarch64", "arm64"]:
      arch = "arm64"
    else:
      raise RuntimeError(f"Unsupported architecture: {machine}")

    ext = "zip" if system == "windows" else "tar.gz"

    return os_name, arch, ext

  def _install_frp(self) -> Path:
    """Download and install FRP binary if not already present.

    Returns:
        Path to the frpc binary.

    Raises:
        RuntimeError: If installation fails.
    """
    FRP_DIR.mkdir(parents=True, exist_ok=True)

    os_name, arch, ext = self._get_platform_info()
    bin_name = "frpc.exe" if os_name == "windows" else "frpc"
    bin_path = FRP_DIR / bin_name

    # Check if binary already exists
    if bin_path.exists():
      return bin_path

    # Construct download URL
    folder_name = f"frp_{FRP_VERSION}_{os_name}_{arch}"
    filename = f"{folder_name}.{ext}"
    url = f"https://github.com/fatedier/frp/releases/download/v{FRP_VERSION}/{filename}"

    try:
      # Download to temp file
      with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as tmp:
        tmp_path = Path(tmp.name)

      urllib.request.urlretrieve(url, tmp_path)

      # Extract
      extract_dir = FRP_DIR / "extract_tmp"
      extract_dir.mkdir(exist_ok=True)

      if ext == "zip":
        with zipfile.ZipFile(tmp_path, "r") as z:
          z.extractall(extract_dir)
      else:
        with tarfile.open(tmp_path, "r:gz") as t:
          t.extractall(extract_dir)

      # Move binary
      src = extract_dir / folder_name / bin_name
      if bin_path.exists():
        bin_path.unlink()
      shutil.move(str(src), str(bin_path))

      # Cleanup
      tmp_path.unlink()
      shutil.rmtree(extract_dir, ignore_errors=True)

      # Make executable on Unix
      if os_name != "windows":
        bin_path.chmod(0o755)

      return bin_path

    except Exception as e:
      raise RuntimeError(f"Failed to install FRP: {e}") from e

  def _create_config(self) -> Path:
    """Create FRP client configuration file.

    Returns:
        Path to the configuration file.
    """
    FRP_DIR.mkdir(parents=True, exist_ok=True)

    config_path = FRP_DIR / f"frpc_{self.config.session_id}.yml"
    # port should be changed when we use load balancing
    yaml_content = f"""
serverAddr: {self.config.server_url}
serverPort: 7000
auth:
  method: token
  token: "{self.config.token}"

transport:
  protocol: "websocket"
  tls:
    enable: true
    serverName: "{self.config.server_url}"

proxies:
  - name: "socks5_tunnel_{self.config.session_id}"
    type: "tcp"
    remotePort: {self.config.remote_port}
    plugin:
      type: "socks5"
"""
    config_path.write_text(yaml_content)
    return config_path

  def start(self) -> None:
    """Start the FRP proxy tunnel.

    Raises:
        RuntimeError: If the proxy fails to start or is already running.
    """
    with self._state.lock:
      if self._state.process is not None:
        raise RuntimeError("Proxy is already running")

      try:
        # Install FRP if needed
        self._bin_path = self._install_frp()

        # Create config
        self._state.config_file = self._create_config()

        # Build command
        cmd = [str(self._bin_path), "-c", str(self._state.config_file)]

        # Start process
        self._state.process = subprocess.Popen(
          cmd,
          stdout=None,
          stderr=None,
        )

        # Give it a moment to start and check if it failed immediately
        try:
            # Wait for the process to exit or timeout
            stdout_data, stderr_data = self._state.process.communicate(timeout=1.0)

            # If we get here, the process exited within 1 second
            stderr = stderr_data.decode() if stderr_data else ""
            stdout = stdout_data.decode() if stdout_data else ""
            self._cleanup()
            raise RuntimeError(f"FRP process exited immediately: {stderr}. Output: {stdout}")

        except subprocess.TimeoutExpired:
            # Process is still running after 1 second
            pass

      except Exception as e:
        self._cleanup()
        if isinstance(e, RuntimeError):
          raise
        raise RuntimeError(f"Failed to start proxy: {e}") from e

  def stop(self) -> None:
    """Stop the FRP proxy tunnel."""
    with self._state.lock:
      self._cleanup()

  def _cleanup(self) -> None:
    """Internal cleanup method."""
    if self._state.process is not None:
      try:
        self._state.process.terminate()
        try:
          self._state.process.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
          self._state.process.kill()
          self._state.process.wait()
      except Exception:
        pass
      self._state.process = None

    if self._state.config_file is not None:
      try:
        if self._state.config_file.exists():
          self._state.config_file.unlink()
      except Exception:
        pass
      self._state.config_file = None

  @property
  def is_running(self) -> bool:
    """Check if the proxy is currently running."""
    with self._state.lock:
      if self._state.process is None:
        return False
      return self._state.process.poll() is None

  def __enter__(self) -> "FRPProxy":
    """Context manager entry."""
    self.start()
    return self

  def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
    """Context manager exit."""
    self.stop()


# Proxy state persistence (stub for CLI compatibility)
def get_proxy_credentials() -> None:
  """Get credentials for a running proxy (if any).

  Returns:
      None - proxy state persistence not yet implemented.
  """
  return None
