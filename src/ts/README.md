# Smooth Typescript SDK

The Smooth Typescript SDK provides a convenient way to interact with the Smooth API for programmatic browser automation and task execution.

## Features

*   **Task Management**: Easily run tasks and retrieve results upon completion.
*   **Interactive Browser Sessions**: Get access to, interact with, and delete stateful browser sessions to manage your login credentials.
*   **Advanced Task Configuration**: Customize task execution with options for device type, session recording, stealth mode, and proxy settings.

## Installation

You can install the Smooth Typescript SDK as follows:

```bash
npm installl @circlemind-ai/smooth-ts
```

## Usage

This sdk is automatically generated from the [Smooth Python SDK](https://docs.smooth.sh/quickstart), so refer to its documentation for details.

### Quick Start

Submit a task in seconds:

```typescript
import { SmoothClient } from "@circlemind-ai/smooth-ts";

const client = new SmoothClient({
  api_key: process.env.CIRCLEMIND_API_KEY,
});

const task = await client.run({
  task: "Go to google flights and find the cheapest flight from London to Paris today",
})

console.log("Live URL:", await task.live_url())
console.log("Agent response:", await task.result())
```