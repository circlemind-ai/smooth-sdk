"""Command-line interface for Smooth browser automation."""

import argparse
import asyncio
import json
import os
import signal
import sys
from typing import Any, cast

from smooth import SmoothAsyncClient, SmoothClient
from smooth._exceptions import ApiError
from smooth._interface import AsyncSessionHandle, AsyncTaskHandle
from smooth._proxy import (
  clear_proxy_state,
  get_proxy_credentials,
  is_proxy_running,
  load_proxy_state,
  save_proxy_state,
)


def print_json(data: Any):
  """Print data as formatted JSON."""
  print(json.dumps(data, indent=2, default=str))


def print_error(message: str):
  """Print error message to stderr."""
  print(f"Error: {message}", file=sys.stderr)
  sys.exit(1)


def load_api_key():
  """Load API key from environment."""
  api_key = os.getenv("CIRCLEMIND_API_KEY")
  if not api_key:
    print_error("CIRCLEMIND_API_KEY environment variable not set")
  return api_key


async def create_profile(args: argparse.Namespace):
  """Create a new browser profile."""
  try:
    async with SmoothAsyncClient() as client:
      profile = await client.create_profile(profile_id=args.profile_id)
      print("Profile created successfully!")
      print(f"Profile ID: {profile.id}")
      if args.json:
        print_json({"id": profile.id})
  except ApiError as e:
    print_error(f"Failed to create profile: {e.detail}")
  except Exception as e:
    print_error(f"Unexpected error: {str(e)}")


async def list_profiles(args: argparse.Namespace):
  """List all browser profiles."""
  try:
    async with SmoothAsyncClient() as client:
      profiles = await client.list_profiles()
      if args.json:
        print_json([{"id": p.id} for p in profiles])
      else:
        if not profiles:
          print("No profiles found.")
        else:
          print(f"Found {len(profiles)} profile(s):")
          for profile in profiles:
            print(f"  - {profile.id}")
  except ApiError as e:
    print_error(f"Failed to list profiles: {e.detail}")
  except Exception as e:
    print_error(f"Unexpected error: {str(e)}")


async def delete_profile(args: argparse.Namespace):
  """Delete a browser profile."""
  try:
    async with SmoothAsyncClient() as client:
      await client.delete_profile(args.profile_id)
      print(f"Profile '{args.profile_id}' deleted successfully!")
  except ApiError as e:
    print_error(f"Failed to delete profile: {e.detail}")
  except Exception as e:
    print_error(f"Unexpected error: {str(e)}")


async def upload_file(args: argparse.Namespace):
  """Upload a file and get its file ID."""
  try:
    async with SmoothAsyncClient() as client:
      with open(args.file_path, "rb") as f:
        result = await client.upload_file(f, name=args.name, purpose=args.purpose)
        print("File uploaded successfully!")
        print(f"File ID: {result.id}")
        if args.json:
          print_json({"file_id": result.id, "name": args.name or args.file_path})
  except FileNotFoundError:
    print_error(f"File not found: {args.file_path}")
  except ApiError as e:
    print_error(f"Failed to upload file: {e.detail}")
  except Exception as e:
    print_error(f"Unexpected error: {str(e)}")


async def delete_file(args: argparse.Namespace):
  """Delete an uploaded file."""
  try:
    async with SmoothAsyncClient() as client:
      await client.delete_file(args.file_id)
      print(f"File '{args.file_id}' deleted successfully!")
  except ApiError as e:
    print_error(f"Failed to delete file: {e.detail}")
  except Exception as e:
    print_error(f"Unexpected error: {str(e)}")


async def start_session(args: argparse.Namespace):
  """Start a browser session."""
  try:
    client = SmoothAsyncClient()
    await client.__aenter__()

    # Parse allowed URLs
    allowed_urls = None
    if args.allowed_urls:
      allowed_urls = [u.strip() for u in args.allowed_urls.split(",")]

    # Parse files list
    files = None
    if args.files:
      files = [f.strip() for f in args.files.split(",")]

    # Check for proxy credentials
    proxy_server = None
    proxy_username = None
    proxy_password = None
    proxy_credentials = get_proxy_credentials()
    if proxy_credentials:
      proxy_server = proxy_credentials.url
      proxy_username = proxy_credentials.username
      proxy_password = proxy_credentials.password
      print(f"Using proxy: {proxy_credentials.url}")

    task_handle = await client.session(
      url=args.url,
      files=files,
      profile_id=args.profile_id,
      profile_read_only=args.profile_read_only,
      device=args.device,
      allowed_urls=allowed_urls,
      enable_recording=False,  # Disabled by default
      stealth_mode=True,  # Enabled by default
      use_adblock=True,  # Enabled by default
      proxy_server=proxy_server,
      proxy_username=proxy_username,
      proxy_password=proxy_password,
      show_cursor=True,  # Show mouse cursor by default
    )

    session_id = task_handle.id()
    print("Session started successfully!")
    print(f"Session ID: {session_id}")

    # Get live URL
    try:
      live_url = await task_handle.live_url(interactive=True, timeout=30)
      print(f"Live URL: {live_url}")

      if args.json:
        print_json({"session_id": session_id, "live_url": live_url})
    except Exception as e:
      print(f"Warning: Could not get live URL: {e}")
      if args.json:
        print_json({"session_id": session_id})

    # Don't close the client - session stays alive
    print("\nSession is running. Use 'smooth close session <session-id>' to close it.")

  except ApiError as e:
    print_error(f"Failed to start session: {e.detail}")
  except Exception as e:
    print_error(f"Unexpected error: {str(e)}")


async def close_session(args: argparse.Namespace):
  """Close a browser session."""
  try:
    async with SmoothAsyncClient() as client:
      session_handle = AsyncSessionHandle(args.session_id, client)
      await session_handle.close(force=args.force)
      print(f"Session '{args.session_id}' closed successfully!")
      if args.force:
        print("Note: Session forcefully terminated. Wait 5 seconds for the profile to save cookies and state.")
      else:
        print("Note: Graceful close initiated. Wait 5 seconds for the profile to save cookies and state.")
  except ApiError as e:
    print_error(f"Failed to close session: {e.detail}")
  except Exception as e:
    print_error(f"Unexpected error: {str(e)}")


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
      print(f"Running task in session '{args.session_id}': {args.task}")

      session_handle = AsyncSessionHandle(args.session_id, client)

      try:
        result = await session_handle.run_task(
          task=args.task,
          url=args.url,
          metadata=metadata,
          response_model=response_model,
          max_steps=args.max_steps,
        )
        print("\nTask completed. Result:")
        if args.json:
          print_json(result.output)
        else:
          print(result.output)
      except Exception as e:
        print_error(f"Failed to run task: {str(e)}")
  except ApiError as e:
    print_error(f"Failed to run task: {e.detail}")
  except Exception as e:
    print_error(f"Unexpected error: {str(e)}")


async def live_view(args: argparse.Namespace):
  """Get the live view URL for a session."""
  try:
    async with SmoothAsyncClient() as client:
      session_handle = AsyncSessionHandle(args.session_id, client)
      live_url = await session_handle.live_url(interactive=True, timeout=30)

      print(f"Live view URL for session '{args.session_id}':")
      print(live_url)
      print("\nOpen this URL in your browser to view and interact with the session.")

      if args.json:
        print_json({"session_id": args.session_id, "live_url": live_url})

  except ApiError as e:
    print_error(f"Failed to get live view: {e.detail}")
  except Exception as e:
    print_error(f"Unexpected error: {str(e)}")


async def download_files(args: argparse.Namespace):
  """Get the download URL for files from a session."""
  try:
    async with SmoothAsyncClient() as client:
      task_handle = AsyncTaskHandle(args.session_id, client)
      downloads_url = await task_handle.downloads_url(timeout=30)

      print(f"Downloads URL for session '{args.session_id}':")
      print(downloads_url)
      print("\nDownload the files from this URL.")

      if args.json:
        print_json({"session_id": args.session_id, "downloads_url": downloads_url})

  except ApiError as e:
    print_error(f"Failed to get downloads: {e.detail}")
  except Exception as e:
    print_error(f"Unexpected error: {str(e)}")


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

      # Navigate to URL if provided
      if args.url:
        print(f"Navigating to {args.url}...")
        await session_handle.goto(args.url)
        print("Waiting 5 seconds for page to load...")
        await asyncio.sleep(5)

      print(f"Extracting data from session '{args.session_id}'...")
      result = await session_handle.extract(schema=cast(dict[str, Any], schema), prompt=args.prompt)

      print("\nExtracted data:")
      if args.json:
        print_json(result.output)
      else:
        print(result.output)

  except ApiError as e:
    print_error(f"Failed to extract data: {e.detail}")
  except Exception as e:
    print_error(f"Unexpected error: {str(e)}")


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

      print(f"Executing JavaScript in session '{args.session_id}'...")
      result = await session_handle.evaluate_js(code=args.code, args=js_args)

      print("\nResult:")
      if args.json:
        print_json(result.output)
      else:
        print(result.output)

  except ApiError as e:
    print_error(f"Failed to evaluate JavaScript: {e.detail}")
  except Exception as e:
    print_error(f"Unexpected error: {str(e)}")


def start_proxy(args: argparse.Namespace):
  """Start a local proxy with public tunnel exposure."""
  # Check if proxy is already running
  if is_proxy_running():
    creds = load_proxy_state()
    if creds:
      print("Proxy is already running!")
    return

  # Create client and start proxy using client method
  client = SmoothClient()

  def signal_handler(sig: Any, frame: Any):
    print("\nStopping proxy...")
    try:
      client.stop_proxy()
    except Exception:
      pass
    clear_proxy_state()
    sys.exit(0)

  signal.signal(signal.SIGINT, signal_handler)
  signal.signal(signal.SIGTERM, signal_handler)

  print(f"Starting proxy on port {args.port} with {args.provider} tunnel...")

  try:
    # Start proxy using client method
    proxy_config = client.start_proxy(
      provider=args.provider,
      port=args.port,
      timeout=args.timeout,
      verbose=args.verbose,
    )

    # Save state for CLI management
    from smooth._proxy import ProxyCredentials

    credentials = ProxyCredentials(
      url=proxy_config["proxy_server"],
      username=proxy_config["proxy_username"],
      password=proxy_config["proxy_password"],
      local_port=args.port,
      pid=None,  # Not needed for CLI state
    )
    save_proxy_state(credentials)

    print("\nProxy is running!")
    print("\nThe proxy will be automatically used by 'smooth start-session'.")
    print("Press Ctrl+C to stop.\n")

    # Keep process alive
    signal.pause()

  except Exception as e:
    print(f"Error: {e}")
    clear_proxy_state()
    sys.exit(1)


def proxy_status(args: argparse.Namespace):
  """Show the status of the proxy."""
  if is_proxy_running():
    creds = load_proxy_state()
    if creds:
      print("Proxy is running!")
      print(f"  URL:      {creds.url}")
      print(f"  Username: {creds.username}")
      print(f"  Password: {creds.password}")
      if args.json:
        print_json(
          {
            "running": True,
            "url": creds.url,
            "username": creds.username,
            "password": creds.password,
          }
        )
  else:
    print("No proxy is currently running.")
    if args.json:
      print_json({"running": False})


def main():
  """Main CLI entry point."""
  parser = argparse.ArgumentParser(
    prog="smooth",
    description="Browser automation for AI agents",
    formatter_class=argparse.RawDescriptionHelpFormatter,
  )

  subparsers = parser.add_subparsers(dest="command", help="Available commands")

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
  start_session_parser.add_argument("--json", action="store_true", help="Output as JSON")
  start_session_parser.set_defaults(func=start_session)

  # close-session command
  close_session_parser = subparsers.add_parser("close-session", help="Close a browser session")
  close_session_parser.add_argument("session_id", help="Session ID to close")
  close_session_parser.add_argument(
    "--force", action="store_true", help="Force close the session immediately (default is graceful close)"
  )
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
  start_proxy_parser = subparsers.add_parser("start-proxy", help="Start a local proxy with public tunnel exposure")
  start_proxy_parser.add_argument(
    "--provider",
    choices=["cloudflare", "serveo", "microsoft"],
    default="cloudflare",
    help="Tunnel provider (default: cloudflare)",
  )
  start_proxy_parser.add_argument("--port", type=int, default=59438, help="Local port (default: 8888)")
  start_proxy_parser.add_argument("--timeout", type=int, default=30, help="Tunnel timeout in seconds (default: 30)")
  start_proxy_parser.add_argument("--verbose", action="store_true", help="Enable verbose output")
  start_proxy_parser.add_argument("--tcp", action="store_true", help="Use TCP mode (serveo only)")
  start_proxy_parser.set_defaults(func=start_proxy)

  # proxy-status command
  proxy_status_parser = subparsers.add_parser("proxy-status", help="Show the status of the proxy")
  proxy_status_parser.add_argument("--json", action="store_true", help="Output as JSON")
  proxy_status_parser.set_defaults(func=proxy_status)

  # Parse arguments
  args = parser.parse_args()

  if not args.command:
    parser.print_help()
    sys.exit(1)

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
