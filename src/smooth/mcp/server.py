"""Smooth SDK MCP Server Implementation.

This module provides the SmoothMCP class that integrates the Smooth SDK
with the Model Context Protocol for AI assistant interactions.
"""

import asyncio
import os
from typing import Annotated, Any, Dict, Literal, Optional

try:
  from fastmcp import Context, FastMCP
  from fastmcp.exceptions import ResourceError
  from pydantic import Field
except ImportError as e:
  raise ImportError("FastMCP is required for MCP functionality. Install with: pip install smooth-py[mcp]") from e

from .. import ApiError, SmoothAsyncClient, TimeoutError


class SmoothMCP:
  """MCP server for Smooth SDK browser automation agent.

  This class provides a Model Context Protocol server that exposes
  Smooth SDK functionality to AI assistants and other MCP clients.

  Example:
      ```python
      from smooth.mcp import SmoothMCP

      # Create and run the MCP server
      mcp = SmoothMCP(api_key="your-api-key")
      mcp.run()  # Runs with STDIO transport by default

      # Or run with HTTP transport
      mcp.run(transport="http", host="0.0.0.0", port=8000)
      ```
  """

  def __init__(
    self,
    api_key: Optional[str] = None,
    server_name: str = "Smooth Browser Agent",
    base_url: Optional[str] = None,
  ):
    """Initialize the Smooth MCP server.

    Args:
        api_key: Smooth API key. If not provided, will use CIRCLEMIND_API_KEY env var.
        server_name: Name for the MCP server.
        base_url: Base URL for the Smooth API (optional).
    """
    self.api_key = api_key or os.getenv("CIRCLEMIND_API_KEY")
    if not self.api_key:
      raise ValueError("API key is required. Provide it directly or set CIRCLEMIND_API_KEY environment variable.")

    self.base_url = base_url
    self.server_name = server_name

    # Initialize FastMCP server
    self._mcp = FastMCP(server_name)
    self._smooth_client: Optional[SmoothAsyncClient] = None

    # Register tools and resources
    self._register_tools()
    self._register_resources()

  async def _get_smooth_client(self) -> SmoothAsyncClient:
    """Get or create the Smooth client instance."""
    if self._smooth_client is None:
      kwargs = {"api_key": self.api_key}
      if self.base_url:
        kwargs["base_url"] = self.base_url
      self._smooth_client = SmoothAsyncClient(**kwargs)
    return self._smooth_client

  def _register_tools(self):
    """Register MCP tools."""

    @self._mcp.tool(
      name="run_browser_task",
      description=(
        "Execute browser automation tasks using natural language descriptions. "
        "Supports both desktop and mobile devices with optional profile state, recording, and advanced configuration."
      ),
      annotations={"title": "Run Browser Task", "readOnlyHint": False, "destructiveHint": False, "openWorldHint": True},
    )
    async def run_browser_task(
      ctx: Context,
      task: Annotated[
        str,
        Field(
          description=(
            "Natural language description of the browser automation task to perform "
            "(e.g., 'Go to Google and search for FastMCP', 'Fill out the contact form with test data at this url: ...')"
          )
        ),
      ],
      device: Annotated[
        Literal["desktop", "mobile"],
        Field(
          description=(
            "Device type for browser automation. Desktop provides full browser experience, "
            "mobile uses a mobile viewport. Mobile is preferred as mobile web pages are lighter and easier to interact with"
          )
        ),
      ] = "mobile",
      max_steps: Annotated[
        int,
        Field(
          description=(
            "Maximum number of steps the agent can take to complete the task. "
            "Higher values allow more complex multi-step workflows"
          ),
          ge=2,
          le=128,
        ),
      ] = 32,
      enable_recording: Annotated[
        bool,
        Field(
          description="Whether to record video of the task execution. Recordings can be used for debugging and verification"
        ),
      ] = True,
      profile_id: Annotated[
        Optional[str],
        Field(
          description=(
            "Browser profile ID to pass login credentials to the agent. "
            "The user must have already created and manually populated a profile and provide the profile ID."
          )
        ),
      ] = None,
      # stealth_mode: Annotated[
      #   bool,
      #   Field(
      #     description=(
      #       "Run browser in stealth mode to avoid detection by anti-bot systems. "
      #       "Useful for accessing sites that block automated browsers"
      #     )
      #   ),
      # ] = True,
      # proxy_server: Annotated[
      #   Optional[str],
      #   Field(
      #     description=(
      #       "Proxy server URL to route browser traffic through. "
      #       "Must include protocol (e.g., 'http://proxy.example.com:8080')"
      #     )
      #   ),
      # ] = None,
      # proxy_username: Annotated[Optional[str], Field(description="Username for proxy server authentication")] = None,
      # proxy_password: Annotated[Optional[str], Field(description="Password for proxy server authentication")] = None,
      timeout: Annotated[
        int,
        Field(
          description=(
            "Maximum time to wait for task completion in seconds. Increase for complex tasks that may take longer."
            " Max 15 minutes."
          ),
          ge=30,
          le=60*15,
        ),
      ] = 60*15,
    ) -> Dict[str, Any]:
      """Run a browser automation task using the Smooth SDK.

      Args:
          ctx: MCP context for logging and communication
          task: Natural language description of the task to perform
          device: Device type ("desktop" or "mobile", default: "mobile")
          max_steps: Maximum steps for the agent (2-128, default: 32)
          enable_recording: Whether to record the execution (default: True)
          profile_id: Optional browser profile ID to maintain state
          stealth_mode: Run in stealth mode to avoid detection (default: False)
          proxy_server: Proxy server URL (must include protocol)
          proxy_username: Proxy authentication username
          proxy_password: Proxy authentication password
          timeout: Maximum time to wait for completion in seconds (default: 300)

      Returns:
          Dictionary containing task results, status, and URLs
      """
      try:
        await ctx.info(f"Starting browser task: {task}")

        # Validate device parameter
        if device not in ["desktop", "mobile"]:
          raise ValueError("Device must be 'desktop' or 'mobile'")

        # Validate max_steps
        if not (2 <= max_steps <= 128):
          raise ValueError("max_steps must be between 2 and 128")

        client = await self._get_smooth_client()

        # Submit the task
        task_handle = await client.run(
          task=task,
          device=device,  # type: ignore
          max_steps=max_steps,
          enable_recording=enable_recording,
          profile_id=profile_id,
          stealth_mode=False,
          proxy_server=None,
          proxy_username=None,
          proxy_password=None,
        )

        await ctx.info(f"Task submitted with ID: {task_handle.id}")

        # Wait for completion
        await ctx.info("Waiting for task completion...")
        result = await task_handle.result(timeout=timeout)

        # Prepare response
        response = {
          "task_id": task_handle.id,
          "status": result.status,
          "output": result.output,
          "credits_used": result.credits_used,
          "device": result.device,
        }

        if result.recording_url:
          response["recording_url"] = result.recording_url
          await ctx.info(f"Recording available at: {result.recording_url}")

        if result.status == "done":
          await ctx.info("Task completed successfully!")
        else:
          await ctx.error(f"Task failed with status: {result.status}")

        return response

      except ApiError as e:
        error_msg = f"Smooth API error: {e.detail}"
        await ctx.error(error_msg)
        raise Exception(error_msg) from None
      except TimeoutError as e:
        error_msg = f"Task timed out: {str(e)}"
        await ctx.error(error_msg)
        raise Exception(error_msg) from None
      except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        await ctx.error(error_msg)
        raise Exception(error_msg) from None

    @self._mcp.tool(
      name="create_browser_profile",
      description=(
        "Create a new browser profile to store user credentials. "
        "Returns a profile ID and live URL that need to be returned to the user to log in into various websites. "
        "Once the user confirms they have logged in to the desired websites, the profile ID can be used in subsequent tasks "
        " to access the user's authenticated state."
      ),
      annotations={"title": "Create Browser profile", "readOnlyHint": False, "destructiveHint": False},
    )
    async def create_browser_profile(
      ctx: Context,
      profile_id: Annotated[
        Optional[str],
        Field(
          description=(
            "Optional custom profile ID. If not provided, a random one will be generated. "
            "Use meaningful names for easier profile management"
          )
        ),
      ] = None,
    ) -> Dict[str, Any]:
      """Create a new browser profile to maintain state between tasks.

      Args:
          ctx: MCP context for logging and communication
          profile_id: Optional custom profile ID. If not provided, a random one will be generated.

      Returns:
          Dictionary containing profile details and live URL
      """
      try:
        await ctx.info("Creating browser profile" + (f" with ID: {profile_id}" if profile_id else ""))

        client = await self._get_smooth_client()
        profile_handle = await client.open_profile(profile_id=profile_id)

        response = {
          "profile_id": profile_handle.browser_profile.profile_id,
          "live_url": profile_handle.browser_profile.live_url,
        }

        await ctx.info(f"Browser profile created: {response['profile_id']}")
        await ctx.info(f"Live profile URL: {response['live_url']}")

        return response

      except ApiError as e:
        error_msg = f"Failed to create browser profile: {e.detail}"
        await ctx.error(error_msg)
        raise Exception(error_msg) from None
      except Exception as e:
        error_msg = f"Unexpected error creating profile: {str(e)}"
        await ctx.error(error_msg)
        raise Exception(error_msg) from None

    @self._mcp.tool(
      name="list_browser_profiles",
      description=(
        "Retrieve a list of all saved browser profiles. "
        "Shows profile IDs that can be passed to future tasks to access login credentials."
      ),
      annotations={"title": "List Browser profiles", "readOnlyHint": True, "destructiveHint": False},
    )
    async def list_browser_profiles(ctx: Context) -> Dict[str, Any]:
      """List all existing browser profiles.

      Args:
          ctx: MCP context for logging and communication

      Returns:
          Dictionary containing list of profile IDs
      """
      try:
        await ctx.info("Retrieving browser profiles...")

        client = await self._get_smooth_client()
        profiles = await client.list_profiles()

        response = {
          "profile_ids": profiles.profile_ids,
          "total_profiles": len(profiles.profile_ids),
        }

        await ctx.info(f"Found {len(profiles.profile_ids)} browser profiles")

        return response

      except ApiError as e:
        error_msg = f"Failed to list browser profiles: {e.detail}"
        await ctx.error(error_msg)
        raise Exception(error_msg) from None
      except Exception as e:
        error_msg = f"Unexpected error listing profiles: {str(e)}"
        await ctx.error(error_msg)
        raise Exception(error_msg) from None

    @self._mcp.tool(
      name="delete_browser_profile",
      description=(
        "Delete a browser profile and its associated credentials. "
        "This permanently removes the profile and all associated data including cookies and cache."
      ),
      annotations={"title": "Delete Browser profile", "readOnlyHint": False, "destructiveHint": True},
    )
    async def delete_browser_profile(
      ctx: Context,
      profile_id: Annotated[
        str,
        Field(
          description=(
            "The ID of the browser profile to delete. "
            "Once deleted, this profile ID cannot be reused and all associated data will be lost"
          ),
          min_length=1,
        ),
      ],
    ) -> Dict[str, Any]:
      """Delete a browser profile and clean up its data.

      Args:
          ctx: MCP context for logging and communication
          profile_id: The ID of the profile to delete

      Returns:
          Dictionary confirming deletion
      """
      try:
        await ctx.info(f"Deleting browser profile: {profile_id}")

        client = await self._get_smooth_client()
        await client.delete_profile(profile_id)

        response = {
          "deleted_profile_id": profile_id,
          "status": "deleted",
        }

        await ctx.info(f"Browser profile {profile_id} deleted successfully")

        return response

      except ApiError as e:
        error_msg = f"Failed to delete browser profile {profile_id}: {e.detail}"
        await ctx.error(error_msg)
        raise Exception(error_msg) from None
      except Exception as e:
        error_msg = f"Unexpected error deleting profile: {str(e)}"
        await ctx.error(error_msg)
        raise Exception(error_msg) from None

  def _register_resources(self):
    """Register MCP resources with comprehensive documentation and dynamic capabilities."""

    # Static API information with annotations
    @self._mcp.resource(
      "smooth://api/info",
      description="Comprehensive information about the Smooth SDK MCP server and its capabilities",
      annotations={"readOnlyHint": True, "idempotentHint": True},
      tags={"documentation", "api"},
      mime_type="text/markdown",
    )
    async def get_api_info(ctx: Context) -> str:
      """Get detailed information about the Smooth SDK and API."""
      await ctx.info("Providing Smooth SDK API information")
      return f"""# Smooth SDK MCP Server v{self._mcp.server_info.version}

This MCP server provides access to Smooth's browser automation capabilities through the Model Context Protocol.

## Server Information
- **Name**: {self._mcp.server_info.name}
- **Version**: {self._mcp.server_info.version}
- **Request ID**: {ctx.request_id}
- **Base URL**: {self.base_url or "Default (https://api2.circlemind.co/api/v1)"}

## Available Tools

### 🚀 run_browser_task
Execute browser automation tasks using natural language descriptions.
- **Device Support**: Desktop and mobile support
- **Profile Management**: Save and access user credentials
- **Recording**: Video capture of automation

### 🔧 create_browser_profile
Create persistent browser profiles to store and access credentials.
- **Live Viewing**: Real-time browser access for the user to enter their credentials

### 📋 list_browser_profiles
View all active browser profiles.

### 🗑️ delete_browser_profile
Permanently removes profile data when no longer needed.
- **Destructive**: Permanently removes profile data

## Configuration

Set your API key using the CIRCLEMIND_API_KEY environment variable:
```bash
export CIRCLEMIND_API_KEY="your-api-key-here"
```

## Best Practices

1. **Use profiles**: Ask the user to create profiles for tasks requiring login and then use them.
2. **Descriptive Tasks**: Use clear, specific task descriptions.
3. **Error Handling**: Check task results for success/failure status
"""

    # Dynamic examples resource with path parameters
    @self._mcp.resource(
      "smooth://examples/{category}",
      description="Get task examples for specific categories of browser automation",
      annotations={"readOnlyHint": True, "idempotentHint": True},
      tags={"examples", "templates", "dynamic"},
      mime_type="text/markdown",
    )
    async def get_category_examples(category: str, ctx: Context) -> str:
      """Get examples for a specific category of browser automation tasks."""
      await ctx.info(f"Providing examples for category: {category}")

      examples_db = {
        "scraping": """# Web Scraping Examples

## Basic Data Extraction
- "Go to example.com and extract all product prices"
- "Navigate to news.ycombinator.com and get the top 10 story titles"
- "Visit Wikipedia and search for 'artificial intelligence', then summarize the first paragraph"

## E-commerce Data
- "Extract product details from Amazon search results for 'wireless headphones'"
- "Get all customer reviews from the first product page"
- "Compare prices across multiple product listings"

## Social Media
- "Scrape the latest 20 tweets from a public Twitter profile"
- "Extract post engagement metrics from Instagram"
- "Get trending topics from Reddit front page"
""",
        "forms": """# Form Automation Examples

## Contact Forms
- "Go to contact form at example.com and fill it with test data"
- "Fill out the newsletter signup with email: test@example.com"
- "Submit a support request with priority: high"

## Registration
- "Navigate to signup page and create an account with random details"
- "Complete user registration with name: John Doe, email: john@test.com"
- "Fill out profile information after account creation"

## Applications
- "Fill out the job application form with my resume information"
- "Complete the rental application with provided details"
- "Submit a loan application with financial information"
""",
        "testing": """# Testing & QA Examples

## Functionality Testing
- "Test the checkout flow on our e-commerce site"
- "Verify all links on the homepage are working"
- "Check if the contact form is submitting properly"

## UI/UX Testing
- "Test responsive design by switching between desktop and mobile"
- "Verify navigation menu works on all pages"
- "Check loading times for key user journeys"

## Integration Testing
- "Test login flow with valid and invalid credentials"
- "Verify payment processing with test cards"
- "Check email verification workflow"
""",
        "social": """# Social Media Automation Examples

## Content Management
- "Post a status update on Twitter" (requires login profile)
- "Upload an image to Instagram with caption" (requires login profile)
- "Share an article on LinkedIn with comment" (requires login profile)

## Engagement
- "Like the latest 10 posts in my feed" (requires login profile)
- "Reply to mentions and messages" (requires login profile)
- "Follow accounts based on specific criteria" (requires login profile)

## Analytics
- "Check latest posts performance metrics" (requires login profile)
- "Download engagement reports" (requires login profile)
- "Monitor brand mentions across platforms" (requires login profile)
""",
      }

      if category not in examples_db:
        available_categories = ", ".join(examples_db.keys())
        raise ResourceError(f"Category '{category}' not found. Available categories: {available_categories}")

      return examples_db[category]

  def run(self, **kwargs):
    """Run the MCP server.

    Args:
        **kwargs: Arguments passed to FastMCP.run() such as transport, host, port, etc.
    """
    try:
      self._mcp.run(**kwargs)
    finally:
      # Clean up on exit
      asyncio.run(self._cleanup())

  async def _cleanup(self):
    """Clean up resources on shutdown."""
    if self._smooth_client:
      await self._smooth_client.close()
      self._smooth_client = None

  @property
  def fastmcp_server(self) -> FastMCP:
    """Access to the underlying FastMCP server instance.

    This allows advanced users to add custom tools or resources.
    """
    return self._mcp
