# Smooth Python SDK

The Smooth Python SDK provides a convenient way to interact with the Smooth API for programmatic browser automation and task execution. This SDK includes both synchronous and asynchronous clients to suit different programming needs.

## Features

*   **Synchronous and Asynchronous Clients**: Choose between `SyncClient` for traditional sequential programming and `AsyncClient` for high-performance asynchronous applications.
*   **Task Management**: Easily run tasks, check their status, and retrieve results.
*   **Interactive Browser Sessions**: Get access to and manage interactive browser sessions.

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

```python
from smooth import SmoothClient, TaskRequest

with SmoothClient() as client:
    task_payload = TaskRequest(
        task="Go to https://www.google.com and search for 'Smooth SDK'"
    )
    
    try:
        completed_task = client.run(task_payload)
        
        if completed_task.result:
            print("Task Result:", completed_task.result)
        else:
            print("Task Error:", completed_task.error)
            
    except TimeoutError:
        print("The task timed out.")
    except ApiError as e:
        print(f"An API error occurred: {e}")
```

#### Managing Browser Sessions

```python
from smooth import SmoothClient

with SmoothClient() as client:
    # Get a new browser session
    browser_session = client.open_session(session_name="my-test-session")
    print("Live URL:", browser_session.live_url)
    print("Session ID:", browser_session.session_id)

    # List all browser sessions
    sessions = client.list_sessions()
    print("All Session IDs:", sessions.session_ids)
```

### Asynchronous Client

The `SmoothAsyncClient` is designed for use in asynchronous applications, such as those built with `asyncio`, to handle multiple operations concurrently without blocking.

#### Running a Task and Waiting for the Result

```python
import asyncio
from smooth import SmoothAsyncClient, TaskRequest

async def main():
    async with SmoothAsyncClient() as client:
        task_payload = TaskRequest(
            task="Go to Github and search for \"smooth-sdk\""
        )
        
        try:
            completed_task = await client.run(task_payload)
            
            if completed_task.result:
                print("Task Result:", completed_task.result)
            else:
                print("Task Error:", completed_task.error)
                
        except TimeoutError:
            print("The task timed out.")
        except ApiError as e:
            print(f"An API error occurred: {e}")

if __name__ == "__main__":
    asyncio.run(main())
```

#### Managing Browser Sessions

```python
import asyncio
from smooth import SmoothAsyncClient

async def main():
    async with SmoothAsyncClient() as client:
        # Get a new browser session
        browser_session = await client.open_session(session_name="my-async-session")
        print("Live URL:", browser_session.live_url)
        print("Session ID:", browser_session.session_id)

        # List all browser sessions
        sessions = await client.list_sessions()
        print("All Session IDs:", sessions.session_ids)

if __name__ == "__main__":
    asyncio.run(main())
```
