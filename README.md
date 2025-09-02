# Smooth Python SDK

The Smooth Python SDK provides a convenient way to interact with the Smooth API for programmatic browser automation and task execution.

## Features

*   **Synchronous and Asynchronous Clients**: Choose between `SmoothClient` for traditional sequential programming and `SmoothAsyncClient` for high-performance asynchronous applications.
*   **Task Management**: Easily run tasks and retrieve results upon completion.
*   **Interactive Browser Sessions**: Get access to, interact with, and delete stateful browser sessions to manage your login credentials.
*   **Advanced Task Configuration**: Customize task execution with options for device type, session recording, stealth mode, and proxy settings.
*   **🆕 MCP Server**: Use the included Model Context Protocol server to integrate browser automation with AI assistants like Claude Desktop.

## Installation

You can install the Smooth Python SDK using pip:

```bash
pip install smooth-py
```

For MCP server functionality, also install FastMCP:

```bash
pip install fastmcp
```

## Quick Start Options

### Option 1: Direct SDK Usage

Use the SDK directly in your Python applications:

### Option 2: MCP Server (AI Assistant Integration)

Use the included MCP server to integrate browser automation with AI assistants:

#### Installation
```bash
# Install with MCP support
pip install smooth-py[mcp]
```

#### Basic Usage
```python
from smooth.mcp import SmoothMCP

# Create and run the MCP server  
mcp = SmoothMCP(api_key="your-api-key")
mcp.run()  # STDIO transport for Claude Desktop

# Or with HTTP transport for web deployment
mcp.run(transport="http", host="0.0.0.0", port=8000)
```

#### Standalone Script (Backward Compatible)
```bash
# Set your API key
export CIRCLEMIND_API_KEY="your-api-key-here"

# Run the MCP server
python mcp_server.py
```

Then configure your AI assistant (like Claude Desktop) to use the MCP server. See [MCP_README.md](MCP_README.md) for detailed setup instructions.

## Authentication

The SDK requires an API key for authentication. You can provide the API key in two ways:

1.  **Directly in the client constructor**:

    ```python
    from smooth import SmoothClient

    client = SmoothClient(api_key="YOUR_API_KEY")
    ```

2.  **As an environment variable**:

    Set the `CIRCLEMIND_API_KEY` environment variable, and the client will automatically use it.

    ```bash
    export CIRCLEMIND_API_KEY="YOUR_API_KEY"
    ```

    ```python
    from smooth import SmoothClient

    # The client will pick up the API key from the environment variable
    client = SmoothClient()
    ```

## Usage

### Synchronous Client

The `SmoothClient` is ideal for scripts and applications that don't require asynchronous operations.

#### Running a Task and Waiting for the Result

The `run` method returns a `TaskHandle`. You can use the `result()` method on this handle to wait for the task to complete and get its final state.

```python
from smooth import SmoothClient
from smooth.models import ApiError, TimeoutError

with SmoothClient() as client:
    try:
        # The run method returns a handle to the task immediately
        task_handle = client.run(
            task="Go to https://www.google.com and search for 'Smooth SDK'",
            device="desktop",
            enable_recording=True
        )
        print(f"Task submitted with ID: {task_handle.id}")
        print(f"Live view available at: {task_handle.live_url}")

        # The result() method waits for the task to complete
        completed_task = task_handle.result()
        
        if completed_task.status == "done":
            print("Task Result:", completed_task.output)
            print(f"View recording at: {completed_task.recording_url}")
        else:
            print("Task Failed:", completed_task.output)
            
    except TimeoutError:
        print("The task timed out.")
    except ApiError as e:
        print(f"An API error occurred: {e}")
```

#### Managing Browser Sessions

You can create, list, and delete browser sessions to maintain state (like logins) between tasks.

```python
from smooth import SmoothClient

with SmoothClient() as client:
    # Create a new browser session
    browser_session = client.open_session()
    print("Live URL:", browser_session.live_url)
    print("Session ID:", browser_session.session_id)

    # List all browser sessions
    sessions = client.list_sessions()
    print("All Session IDs:", sessions.session_ids)

    # Delete the browser session
    client.delete_session(session_id=session_id)
    print(f"Session '{session_id}' deleted.")
```

### Asynchronous Client

The `SmoothAsyncClient` is designed for use in asynchronous applications, such as those built with `asyncio`, to handle multiple operations concurrently without blocking.

#### Running a Task and Waiting for the Result

The `run` method returns an `AsyncTaskHandle`. Await the `result()` method on the handle to get the final task status.

```python
import asyncio
from smooth import SmoothAsyncClient
from smooth.models import ApiError, TimeoutError

async def main():
    async with SmoothAsyncClient() as client:
        try:
            # The run method returns a handle to the task immediately
            task_handle = await client.run(
                task="Go to Github and search for \"smooth-sdk\""
            )
            print(f"Task submitted with ID: {task_handle.id}")
            print(f"Live view available at: {task_handle.live_url}")

            # The result() method waits for the task to complete
            completed_task = await task_handle.result()
            
            if completed_task.status == "done":
                print("Task Result:", completed_task.output)
            else:
                print("Task Failed:", completed_task.output)
                
        except TimeoutError:
            print("The task timed out.")
        except ApiError as e:
            print(f"An API error occurred: {e}")

if __name__ == "__main__":
    asyncio.run(main())
```

## MCP Server (AI Assistant Integration)

The Smooth SDK includes a Model Context Protocol (MCP) server that allows AI assistants like Claude Desktop or Cursor to perform browser automation tasks through natural language commands.

### Installation

```bash
pip install smooth-py[mcp]
```

### Basic Usage

```python
from smooth.mcp import SmoothMCP

# Create and run the MCP server
mcp = SmoothMCP(api_key="your-api-key")
mcp.run()
```

### Example MCP Usage

Once configured, you can ask your MCP client to perform browser automation:

- "Please go to news.ycombinator.com and get the top 5 story titles"
- "Create a browser session, log into Gmail, and check for unread emails"
- "Go to Amazon and search for wireless headphones under $100"
- "Fill out the contact form at example.com with test data"
