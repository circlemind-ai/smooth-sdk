"""Command-line interface for Smooth browser automation."""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, cast

from smooth import SmoothAsyncClient
from smooth._exceptions import ApiError
from smooth._interface import AsyncSessionHandle, AsyncTaskHandle

# from smooth._proxy import (
#   clear_proxy_state,
#   get_proxy_credentials,
#   is_proxy_running,
#   load_proxy_state,
#   save_proxy_state,
# )


def print_json(data: Any):
  """Print data as formatted JSON."""
  print(json.dumps(data, indent=2, default=str))


def print_success(message: str, data: dict[str, Any] | None = None):
  """Print success response as JSON."""
  result = {"success": True, "message": message}
  if data:
    result.update(data)
  print_json(result)


def print_error_json(message: str):
  """Print error response as JSON to stderr and exit."""
  print(json.dumps({"success": False, "error": message}, indent=2, default=str), file=sys.stderr)
  sys.exit(1)


def print_error(message: str, json_mode: bool = False):
  """Print error message to stderr."""
  if json_mode:
    print_error_json(message)
  else:
    print(f"Error: {message}", file=sys.stderr)
    sys.exit(1)


def get_config_path() -> Path:
  """Get the path to the config file."""
  return Path.home() / ".smooth" / "config.json"


def get_sessions_path() -> Path:
  """Get the path to the sessions file."""
  return Path.home() / ".smooth" / "sessions.json"


def load_sessions() -> dict[str, Any]:
  """Load sessions from ~/.smooth/sessions.json."""
  sessions_path = get_sessions_path()
  if sessions_path.exists():
    try:
      with open(sessions_path) as f:
        return json.load(f)
    except (json.JSONDecodeError, IOError):
      return {"sessions": []}
  return {"sessions": []}


def save_sessions(data: dict[str, Any]):
  """Save sessions to ~/.smooth/sessions.json."""
  sessions_path = get_sessions_path()
  sessions_path.parent.mkdir(parents=True, exist_ok=True)
  with open(sessions_path, "w") as f:
    json.dump(data, f, indent=2)


def add_session(session_id: str, live_url: str | None, device: str, task: str | None = None, proxy_pid: int | None = None):
  """Add a session to the sessions file."""
  from datetime import datetime, timezone

  data = load_sessions()
  session_data = {
    "session_id": session_id,
    "live_url": live_url,
    "device": device,
    "task": task,
    "start_time": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
  }
  if proxy_pid:
    session_data["proxy_pid"] = str(proxy_pid)
  data["sessions"].append(session_data)
  save_sessions(data)


def remove_session(session_id: str):
  """Remove a session from the sessions file."""
  data = load_sessions()
  data["sessions"] = [s for s in data["sessions"] if s.get("session_id") != session_id]
  save_sessions(data)


def update_session_task(session_id: str, task: str | None):
  """Update the task field for a session."""
  data = load_sessions()
  for session in data["sessions"]:
    if session.get("session_id") == session_id:
      session["task"] = task
      break
  save_sessions(data)


def load_config() -> dict[str, Any]:
  """Load configuration from ~/.smooth/config.json."""
  config_path = get_config_path()
  if config_path.exists():
    try:
      with open(config_path) as f:
        return json.load(f)
    except (json.JSONDecodeError, IOError):
      return {}
  return {}


def save_config(config: dict[str, Any]):
  """Save configuration to ~/.smooth/config.json."""
  config_path = get_config_path()
  config_path.parent.mkdir(parents=True, exist_ok=True)
  with open(config_path, "w") as f:
    json.dump(config, f, indent=2)


def load_config_to_env():
  """Load API key from config file into environment if not already set."""
  if not os.getenv("CIRCLEMIND_API_KEY"):
    config = load_config()
    api_key = config.get("api_key")
    if api_key:
      os.environ["CIRCLEMIND_API_KEY"] = api_key


def load_api_key():
  """Load API key from environment."""
  api_key = os.getenv("CIRCLEMIND_API_KEY")
  if not api_key:
    print_error(
      "API key not configured.\n"
      "  1. Get your free API key from https://app.smooth.sh/\n"
      "  2. Run: smooth config --api-key <your-key>"
    )
  return api_key


async def create_profile(args: argparse.Namespace):
  """Create a new browser profile."""
  try:
    async with SmoothAsyncClient() as client:
      profile = await client.create_profile(profile_id=args.profile_id)
      if args.json:
        print_success("Profile created successfully", {"profile_id": profile.id})
      else:
        print("Profile created successfully!")
        print(f"Profile ID: {profile.id}")
  except ApiError as e:
    print_error(f"Failed to create profile: {e.detail}", json_mode=args.json)
  except Exception as e:
    print_error(f"Unexpected error: {str(e)}", json_mode=args.json)


async def list_profiles(args: argparse.Namespace):
  """List all browser profiles."""
  try:
    async with SmoothAsyncClient() as client:
      profiles = await client.list_profiles()
      if args.json:
        print_success(
          f"Found {len(profiles)} profile(s)",
          {"profiles": [{"id": p.id} for p in profiles], "count": len(profiles)}
        )
      else:
        if not profiles:
          print("No profiles found.")
        else:
          print(f"Found {len(profiles)} profile(s):")
          for profile in profiles:
            print(f"  - {profile.id}")
  except ApiError as e:
    print_error(f"Failed to list profiles: {e.detail}", json_mode=args.json)
  except Exception as e:
    print_error(f"Unexpected error: {str(e)}", json_mode=args.json)


async def delete_profile(args: argparse.Namespace):
  """Delete a browser profile."""
  try:
    async with SmoothAsyncClient() as client:
      await client.delete_profile(args.profile_id)
      if args.json:
        print_success(f"Profile '{args.profile_id}' deleted successfully", {"profile_id": args.profile_id})
      else:
        print(f"Profile '{args.profile_id}' deleted successfully!")
  except ApiError as e:
    print_error(f"Failed to delete profile: {e.detail}", json_mode=args.json)
  except Exception as e:
    print_error(f"Unexpected error: {str(e)}", json_mode=args.json)


async def upload_file(args: argparse.Namespace):
  """Upload a file and get its file ID."""
  try:
    async with SmoothAsyncClient() as client:
      with open(args.file_path, "rb") as f:
        result = await client.upload_file(f, name=args.name, purpose=args.purpose)
        if args.json:
          print_success("File uploaded successfully", {"file_id": result.id, "name": args.name or args.file_path})
        else:
          print("File uploaded successfully!")
          print(f"File ID: {result.id}")
  except FileNotFoundError:
    print_error(f"File not found: {args.file_path}", json_mode=args.json)
  except ApiError as e:
    print_error(f"Failed to upload file: {e.detail}", json_mode=args.json)
  except Exception as e:
    print_error(f"Unexpected error: {str(e)}", json_mode=args.json)


async def delete_file(args: argparse.Namespace):
  """Delete an uploaded file."""
  try:
    async with SmoothAsyncClient() as client:
      await client.delete_file(args.file_id)
      if args.json:
        print_success(f"File '{args.file_id}' deleted successfully", {"file_id": args.file_id})
      else:
        print(f"File '{args.file_id}' deleted successfully!")
  except ApiError as e:
    print_error(f"Failed to delete file: {e.detail}", json_mode=args.json)
  except Exception as e:
    print_error(f"Unexpected error: {str(e)}", json_mode=args.json)


async def start_session(args: argparse.Namespace):
  """Start a browser session."""
  client = SmoothAsyncClient()
  try:
    await client.__aenter__()

    # Parse allowed URLs
    allowed_urls = None
    if args.allowed_urls:
      allowed_urls = [u.strip() for u in args.allowed_urls.split(",")]

    # Parse files list
    files = None
    if args.files:
      files = [f.strip() for f in args.files.split(",")]

    # Configure proxy
    proxy_server = None if args.no_proxy else args.proxy_server
    proxy_username = None
    proxy_password = args.proxy_password if hasattr(args, "proxy_password") else None

    if proxy_server and not args.json:
      print(f"Using proxy: {proxy_server}")

    task_handle = await client.session(
      url=args.url,
      files=files,
      profile_id=args.profile_id,
      profile_read_only=args.profile_read_only,
      device=args.device,
      allowed_urls=allowed_urls,
      enable_recording=True,  # Enabled by default
      stealth_mode=True,  # Enabled by default
      use_adblock=True,  # Enabled by default
      proxy_server=proxy_server,
      proxy_username=proxy_username,
      proxy_password=proxy_password,
      show_cursor=True,  # Show mouse cursor by default
    )

    session_id = task_handle.id()

    # Get live URLs (embed=True for sessions.json, embed=False for CLI output)
    live_url = None
    live_url_embed = None
    try:
      live_url = await task_handle.live_url(interactive=True, embed=False, timeout=30)
      live_url_embed = await task_handle.live_url(interactive=True, embed=True, timeout=30)
    except Exception as e:
      if not args.json:
        print(f"Warning: Could not get live URL: {e}")

    # Get proxy PID if running
    proxy_pid = None
    if task_handle._proxy and task_handle._proxy._state.process:  # pyright: ignore[reportPrivateUsage]
      proxy_pid = task_handle._proxy._state.process.pid  # pyright: ignore[reportPrivateUsage]

    # Track session in sessions.json (with embed=True URL)
    add_session(session_id=session_id, live_url=live_url_embed, device=args.device, task=None, proxy_pid=proxy_pid)

    if args.json:
      result = {
        "success": True,
        "message": "Session started successfully",
        "session_id": session_id,
      }
      if live_url:
        result["live_url"] = live_url
      print_json(result)
    else:
      print("Session started successfully!")
      print(f"Session ID: {session_id}")
      if live_url:
        print(f"Live URL: {live_url}")
      print("\nSession is running. Use 'smooth close-session <session-id>' to close it.")

  except ApiError as e:
    print_error(f"Failed to start session: {e.detail}", json_mode=args.json)
  except Exception as e:
    print_error(f"Unexpected error: {str(e)}", json_mode=args.json)
  finally:
    await client.close()


def get_session(session_id: str) -> dict[str, Any] | None:
  """Get a session by ID from the sessions file."""
  data = load_sessions()
  for session in data.get("sessions", []):
    if session.get("session_id") == session_id:
      return session
  return None


def kill_proxy_process(pid: int | str) -> bool:
  """Kill a proxy process by PID."""
  import signal

  try:
    os.kill(int(pid), signal.SIGTERM)
    return True
  except (ProcessLookupError, PermissionError, ValueError):
    return False


async def close_session(args: argparse.Namespace):
  """Close a browser session."""
  # Kill proxy process if it exists (don't let this block the rest)
  session_data = get_session(args.session_id)
  if session_data and session_data.get("proxy_pid"):
    try:
      if kill_proxy_process(session_data["proxy_pid"]):
        if not args.json:
          print("Stopped local proxy tunnel.")
      else:
        if not args.json:
          print("Warning: Could not stop local proxy tunnel (process may have already exited).")
    except Exception as e:
      if not args.json:
        print(f"Warning: Failed to stop local proxy tunnel: {e}")

  # Try to close the session on the server
  api_error = None
  try:
    async with SmoothAsyncClient() as client:
      session_handle = AsyncSessionHandle(args.session_id, client)
      await session_handle.close(force=args.force)
  except ApiError as e:
    api_error = f"Failed to close session: {e.detail}"
  except Exception as e:
    api_error = f"Unexpected error: {str(e)}"

  # Always remove from sessions.json (even if API call failed, local cleanup should happen)
  try:
    remove_session(args.session_id)
  except Exception as e:
    if not args.json:
      print(f"Warning: Failed to remove session from local tracking: {e}")

  # Report result
  if api_error:
    print_error(api_error, json_mode=args.json)
  elif args.json:
    print_success(
      f"Session '{args.session_id}' closed successfully",
      {"session_id": args.session_id, "force": args.force}
    )
  else:
    print(f"Session '{args.session_id}' closed successfully!")
    if args.force:
      print("Note: Session forcefully terminated. Wait 5 seconds for the profile to save cookies and state.")
    else:
      print("Note: Graceful close initiated. Wait 5 seconds for the profile to save cookies and state.")


async def run_task(args: argparse.Namespace):
  """Run a task in an existing browser session."""
  try:
    # Parse metadata if provided
    metadata = None
    if args.metadata:
      try:
        metadata = json.loads(args.metadata)
      except json.JSONDecodeError:
        print_error("Invalid JSON for --metadata")

    # Parse response model if provided
    response_model = None
    if args.response_model:
      try:
        response_model = json.loads(args.response_model)
      except json.JSONDecodeError:
        print_error("Invalid JSON for --response-model")

    async with SmoothAsyncClient() as client:
      if not args.json:
        print(f"Running task in session '{args.session_id}': {args.task}")

      # Update session task in sessions.json
      update_session_task(args.session_id, args.task)

      session_handle = AsyncSessionHandle(args.session_id, client)

      try:
        result = await session_handle.run_task(
          task=args.task,
          url=args.url,
          metadata=metadata,
          response_model=response_model,
          max_steps=args.max_steps,
        )

        # Clear task (session is now idle)
        update_session_task(args.session_id, None)

        if args.json:
          print_success("Task completed successfully", {"session_id": args.session_id, "result": result.output})
        else:
          print("\nTask completed. Result:")
          print(result.output)
      except Exception as e:
        # Clear task on error as well
        update_session_task(args.session_id, None)
        print_error(f"Failed to run task: {str(e)}", json_mode=args.json)
  except ApiError as e:
    print_error(f"Failed to run task: {e.detail}", json_mode=args.json)
  except Exception as e:
    print_error(f"Unexpected error: {str(e)}", json_mode=args.json)


async def live_view(args: argparse.Namespace):
  """Get the live view URL for a session."""
  try:
    async with SmoothAsyncClient() as client:
      session_handle = AsyncSessionHandle(args.session_id, client)
      live_url = await session_handle.live_url(interactive=True, timeout=30)

      if args.json:
        print_success(
          "Live view URL retrieved",
          {"session_id": args.session_id, "live_url": live_url}
        )
      else:
        print(f"Live view URL for session '{args.session_id}':")
        print(live_url)
        print("\nOpen this URL in your browser to view and interact with the session.")

  except ApiError as e:
    print_error(f"Failed to get live view: {e.detail}", json_mode=args.json)
  except Exception as e:
    print_error(f"Unexpected error: {str(e)}", json_mode=args.json)


async def download_files(args: argparse.Namespace):
  """Get the download URL for files from a session."""
  try:
    async with SmoothAsyncClient() as client:
      task_handle = AsyncTaskHandle(args.session_id, client)
      downloads_url = await task_handle.downloads_url(timeout=30)

      if args.json:
        print_success(
          "Downloads URL retrieved",
          {"session_id": args.session_id, "downloads_url": downloads_url}
        )
      else:
        print(f"Downloads URL for session '{args.session_id}':")
        print(downloads_url)
        print("\nDownload the files from this URL.")

  except ApiError as e:
    print_error(f"Failed to get downloads: {e.detail}", json_mode=args.json)
  except Exception as e:
    print_error(f"Unexpected error: {str(e)}", json_mode=args.json)


# async def recording_url(args: argparse.Namespace):
#   """Get the recording URL for a session."""
#   try:
#     async with SmoothAsyncClient() as client:
#       task_handle = AsyncTaskHandle(args.session_id, client)
#       rec_url = await task_handle.recording_url(timeout=30)

#       print(f"Recording URL for session '{args.session_id}':")
#       print(rec_url)
#       print("\nOpen this URL to view the recording.")

#       if args.json:
#         print_json({"session_id": args.session_id, "recording_url": rec_url})

#   except ApiError as e:
#     print_error(f"Failed to get recording: {e.detail}")
#   except Exception as e:
#     print_error(f"Unexpected error: {str(e)}")


async def extract(args: argparse.Namespace):
  """Extract structured data from the current page in a session."""
  try:
    # Parse schema
    schema = None
    if args.schema:
      try:
        schema = json.loads(args.schema)
      except json.JSONDecodeError:
        print_error("Invalid JSON for --schema")
    else:
      print_error("--schema is required")

    async with SmoothAsyncClient() as client:
      session_handle = AsyncSessionHandle(args.session_id, client)

      # Update session task in sessions.json
      update_session_task(args.session_id, "Extracting data")

      try:
        # Navigate to URL if provided
        if args.url:
          if not args.json:
            print(f"Navigating to {args.url}...")
          await session_handle.goto(args.url)
          if not args.json:
            print("Waiting 5 seconds for page to load...")
          await asyncio.sleep(5)

        if not args.json:
          print(f"Extracting data from session '{args.session_id}'...")
        result = await session_handle.extract(schema=cast(dict[str, Any], schema), prompt=args.prompt)

        # Clear task (session is now idle)
        update_session_task(args.session_id, None)

        if args.json:
          print_success("Data extracted successfully", {"session_id": args.session_id, "data": result.output})
        else:
          print("\nExtracted data:")
          print(result.output)
      except Exception as e:
        # Clear task on error
        update_session_task(args.session_id, None)
        raise

  except ApiError as e:
    print_error(f"Failed to extract data: {e.detail}", json_mode=args.json)
  except Exception as e:
    print_error(f"Unexpected error: {str(e)}", json_mode=args.json)


async def evaluate_js(args: argparse.Namespace):
  """Evaluate JavaScript code in the browser context."""
  try:
    # Parse args if provided
    js_args = None
    if args.args:
      try:
        js_args = json.loads(args.args)
      except json.JSONDecodeError:
        print_error("Invalid JSON for --args")

    async with SmoothAsyncClient() as client:
      session_handle = AsyncSessionHandle(args.session_id, client)

      if not args.json:
        print(f"Executing JavaScript in session '{args.session_id}'...")
      result = await session_handle.evaluate_js(code=args.code, args=js_args)

      if args.json:
        print_success("JavaScript executed successfully", {"session_id": args.session_id, "result": result.output})
      else:
        print("\nResult:")
        print(result.output)

  except ApiError as e:
    print_error(f"Failed to evaluate JavaScript: {e.detail}", json_mode=args.json)
  except Exception as e:
    print_error(f"Unexpected error: {str(e)}", json_mode=args.json)


# def start_proxy(args: argparse.Namespace):
#   """Start a local proxy with public tunnel exposure."""
#   # Check if proxy is already running
#   if is_proxy_running():
#     creds = load_proxy_state()
#     if creds:
#       print("Proxy is already running!")
#     return

#   # Create client and start proxy using client method
#   client = SmoothClient()

#   def signal_handler(sig: Any, frame: Any):
#     print("\nStopping proxy...")
#     try:
#       client.stop_proxy()
#     except Exception:
#       pass
#     clear_proxy_state()
#     sys.exit(0)

#   signal.signal(signal.SIGINT, signal_handler)
#   signal.signal(signal.SIGTERM, signal_handler)

#   print(f"Starting proxy on port {args.port} with {args.provider} tunnel...")

#   try:
#     # Start proxy using client method
#     proxy_config = client.start_proxy(
#       provider=args.provider,
#       port=args.port,
#       timeout=args.timeout,
#       verbose=args.verbose,
#     )

#     print(f"Proxy config: {proxy_config}")

#     # Save state for CLI management
#     from smooth._proxy import ProxyCredentials

#     credentials = ProxyCredentials(
#       url=proxy_config["proxy_server"],
#       username=proxy_config["proxy_username"],
#       password=proxy_config["proxy_password"],
#       local_port=args.port,
#       pid=os.getpid(),  # Store PID so proxy-status can detect running proxy
#     )
#     save_proxy_state(credentials)

#     print("\nProxy is running!")
#     print("\nThe proxy will be automatically used by 'smooth start-session'.")
#     print("Press Ctrl+C to stop.\n")

#     # Keep process alive
#     signal.pause()

#   except Exception as e:
#     print(f"Error: {e}")
#     clear_proxy_state()
#     sys.exit(1)


# def proxy_status(args: argparse.Namespace):
#   """Show the status of the proxy."""
#   if is_proxy_running():
#     creds = load_proxy_state()
#     if creds:
#       if args.json:
#         print_success(
#           "Proxy is running",
#           {
#             "running": True,
#             "url": creds.url,
#             "username": creds.username,
#             "password": creds.password,
#           }
#         )
#       else:
#         print("Proxy is running!")
#         print(f"  URL:      {creds.url}")
#         print(f"  Username: {creds.username}")
#         print(f"  Password: {creds.password}")
#   else:
#     if args.json:
#       print_json({"success": True, "message": "No proxy is currently running", "running": False})
#     else:
#       print("No proxy is currently running.")


def config_command(args: argparse.Namespace):
  """Configure the Smooth CLI."""
  config = load_config()

  if args.api_key:
    config["api_key"] = args.api_key
    save_config(config)
    if args.json:
      print_success("API key saved successfully", {"config_file": str(get_config_path())})
    else:
      print("API key saved successfully!")
      print(f"Config file: {get_config_path()}")
  elif args.show:
    if args.json:
      print_success("Configuration retrieved", {"config": config})
    else:
      if not config:
        print("No configuration found.")
      else:
        print(f"Config file: {get_config_path()}")
        if "api_key" in config:
          # Mask the API key for security
          masked_key = config["api_key"][:8] + "..." + config["api_key"][-4:] if len(config["api_key"]) > 12 else "***"
          print(f"API key: {masked_key}")
  else:
    # No arguments, show help
    print("Usage:")
    print("  smooth config --api-key <key>  Save your API key")
    print("  smooth config --show           Show current configuration")


def main():
  """Main CLI entry point."""
  # Load API key from config file into environment
  load_config_to_env()

  parser = argparse.ArgumentParser(
    prog="smooth",
    description="Browser automation for AI agents",
    formatter_class=argparse.RawDescriptionHelpFormatter,
  )

  subparsers = parser.add_subparsers(dest="command", help="Available commands")

  # config command
  config_parser = subparsers.add_parser("config", help="Configure the Smooth CLI")
  config_parser.add_argument("--api-key", help="Set your API key")
  config_parser.add_argument("--show", action="store_true", help="Show current configuration")
  config_parser.add_argument("--json", action="store_true", help="Output as JSON")
  config_parser.set_defaults(func=config_command)

  # create-profile command
  create_profile_parser = subparsers.add_parser("create-profile", help="Create a new browser profile")
  create_profile_parser.add_argument("--profile-id", help="Custom profile ID (optional)")
  create_profile_parser.add_argument("--json", action="store_true", help="Output as JSON")
  create_profile_parser.set_defaults(func=create_profile)

  # list-profiles command
  list_profiles_parser = subparsers.add_parser("list-profiles", help="List all browser profiles")
  list_profiles_parser.add_argument("--json", action="store_true", help="Output as JSON")
  list_profiles_parser.set_defaults(func=list_profiles)

  # delete-profile command
  delete_profile_parser = subparsers.add_parser("delete-profile", help="Delete a browser profile")
  delete_profile_parser.add_argument("profile_id", help="Profile ID to delete")
  delete_profile_parser.add_argument("--json", action="store_true", help="Output as JSON")
  delete_profile_parser.set_defaults(func=delete_profile)

  # upload-file command
  upload_file_parser = subparsers.add_parser("upload-file", help="Upload a file and get its file ID")
  upload_file_parser.add_argument("file_path", help="Path to the file to upload")
  upload_file_parser.add_argument("--name", help="Custom name for the file (optional)")
  upload_file_parser.add_argument("--purpose", help="Description of the file's purpose")
  upload_file_parser.add_argument("--json", action="store_true", help="Output as JSON")
  upload_file_parser.set_defaults(func=upload_file)

  # delete-file command
  delete_file_parser = subparsers.add_parser("delete-file", help="Delete an uploaded file")
  delete_file_parser.add_argument("file_id", help="File ID to delete")
  delete_file_parser.add_argument("--json", action="store_true", help="Output as JSON")
  delete_file_parser.set_defaults(func=delete_file)

  # start-session command
  start_session_parser = subparsers.add_parser("start-session", help="Start a browser session")
  start_session_parser.add_argument("--profile-id", help="Profile ID to use")
  start_session_parser.add_argument("--profile-read-only", action="store_true", help="Load profile in read-only mode")
  start_session_parser.add_argument("--url", help="Starting URL for the session")
  start_session_parser.add_argument("--files", help="Comma-separated list of file IDs to make available in session")
  start_session_parser.add_argument(
    "--device", choices=["mobile", "desktop"], default="mobile", help="Device type (default: mobile)"
  )
  start_session_parser.add_argument("--allowed-urls", help="Comma-separated list of allowed URL patterns")
  # start_session_parser.add_argument("--enable-recording", action="store_true", help="Enable video recording")
  # start_session_parser.add_argument("--no-stealth-mode", action="store_true", help="Disable stealth mode")
  # start_session_parser.add_argument("--no-adblock", action="store_true", help="Disable adblock")
  start_session_parser.add_argument(
    "--proxy-server", default="self", help="Proxy server address ('self' for local tunnel, default: self)"
  )
  start_session_parser.add_argument("--proxy-password", help="Proxy password (auto-generated if not provided)")
  start_session_parser.add_argument("--no-proxy", action="store_true", help="Disable proxy (overrides --proxy-server)")
  start_session_parser.add_argument("--json", action="store_true", help="Output as JSON")
  start_session_parser.set_defaults(func=start_session)

  # close-session command
  close_session_parser = subparsers.add_parser("close-session", help="Close a browser session")
  close_session_parser.add_argument("session_id", help="Session ID to close")
  close_session_parser.add_argument(
    "--force", action="store_true", help="Force close the session immediately (default is graceful close)"
  )
  close_session_parser.add_argument("--json", action="store_true", help="Output as JSON")
  close_session_parser.set_defaults(func=close_session, force=False)

  # run command
  run_parser = subparsers.add_parser("run", help="Run a task in an existing browser session")
  run_parser.add_argument("session_id", help="Session ID to run the task in (must be created first with start-session)")
  run_parser.add_argument("task", help="Task description for the agent")
  run_parser.add_argument("--url", help="URL to navigate to before running the task")
  run_parser.add_argument("--metadata", help="Metadata as JSON string")
  run_parser.add_argument("--response-model", help="JSON schema for structured output")
  run_parser.add_argument("--max-steps", type=int, default=32, help="Maximum steps (default: 32)")
  run_parser.add_argument("--json", action="store_true", help="Output as JSON")
  run_parser.set_defaults(func=run_task)

  # live-view command
  live_parser = subparsers.add_parser("live-view", help="Get live view URL for a session")
  live_parser.add_argument("session_id", help="Session ID to view")
  live_parser.add_argument("--json", action="store_true", help="Output as JSON")
  live_parser.set_defaults(func=live_view)

  # recording-url command
  # recording_parser = subparsers.add_parser("recording-url", help="Get recording URL for a session")
  # recording_parser.add_argument("session_id", help="Session ID to get recording for")
  # recording_parser.add_argument("--json", action="store_true", help="Output as JSON")
  # recording_parser.set_defaults(func=recording_url)

  # downloads command
  download_parser = subparsers.add_parser("downloads", help="Get download URL for files from a session")
  download_parser.add_argument("session_id", help="Session ID to download from")
  download_parser.add_argument("--json", action="store_true", help="Output as JSON")
  download_parser.set_defaults(func=download_files)

  # extract command
  extract_parser = subparsers.add_parser("extract", help="Extract structured data from the current page")
  extract_parser.add_argument("session_id", help="Session ID to extract from")
  extract_parser.add_argument("--schema", required=True, help="JSON schema for extraction")
  extract_parser.add_argument("--url", help="URL to navigate to before extracting (waits 5 seconds after navigation)")
  extract_parser.add_argument("--prompt", help="Optional prompt to guide extraction")
  extract_parser.add_argument("--json", action="store_true", help="Output as JSON")
  extract_parser.set_defaults(func=extract)

  # evaluate-js command
  evaluate_js_parser = subparsers.add_parser("evaluate-js", help="Evaluate JavaScript code in the browser")
  evaluate_js_parser.add_argument("session_id", help="Session ID to execute in")
  evaluate_js_parser.add_argument("code", help="JavaScript code to execute")
  evaluate_js_parser.add_argument("--args", help="JSON object with arguments to pass to the code")
  evaluate_js_parser.add_argument("--json", action="store_true", help="Output as JSON")
  evaluate_js_parser.set_defaults(func=evaluate_js)

  # start-proxy command
  # start_proxy_parser = subparsers.add_parser("start-proxy", help="Start a local proxy with public tunnel exposure")
  # start_proxy_parser.add_argument(
  #   "--provider",
  #   choices=["cloudflare", "serveo", "microsoft"],
  #   default="cloudflare",
  #   help="Tunnel provider (default: cloudflare)",
  # )
  # start_proxy_parser.add_argument("--port", type=int, default=59438, help="Local port (default: 8888)")
  # start_proxy_parser.add_argument("--timeout", type=int, default=30, help="Tunnel timeout in seconds (default: 30)")
  # start_proxy_parser.add_argument("--verbose", action="store_true", help="Enable verbose output")
  # start_proxy_parser.add_argument("--tcp", action="store_true", help="Use TCP mode (serveo only)")
  # start_proxy_parser.set_defaults(func=start_proxy)

  # # proxy-status command
  # proxy_status_parser = subparsers.add_parser("proxy-status", help="Show the status of the proxy")
  # proxy_status_parser.add_argument("--json", action="store_true", help="Output as JSON")
  # proxy_status_parser.set_defaults(func=proxy_status)

  # Parse arguments
  args = parser.parse_args()

  if not args.command:
    parser.print_help()
    sys.exit(1)

  # Commands that don't require an API key
  no_api_key_commands = {"config"}

  # Check for API key if required
  if args.command not in no_api_key_commands:
    load_api_key()

  # Run the appropriate function (sync for proxy commands, async for others)
  if hasattr(args, "func"):
    func = args.func
    if asyncio.iscoroutinefunction(func):
      asyncio.run(func(args))
    else:
      func(args)
  else:
    parser.print_help()
    sys.exit(1)


if __name__ == "__main__":
  main()
