# Smooth Python SDK

The Smooth Python SDK provides a convenient way to interact with the Smooth API for programmatic browser automation and task execution.

## Features

*   **Synchronous and Asynchronous Clients**: Choose between `SmoothClient` for traditional sequential programming and `SmoothAsyncClient` for high-performance asynchronous applications.
*   **Task Management**: Easily run tasks and retrieve results upon completion.
*   **Interactive Browser Sessions**: Get access to, interact with, and delete stateful browser sessions to manage your login credentials.
*   **Advanced Task Configuration**: Customize task execution with options for device type, session recording, stealth mode, and proxy settings.

## Installation

You can install the Smooth Python SDK using pip:

```bash
pip install smooth-py
```

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
