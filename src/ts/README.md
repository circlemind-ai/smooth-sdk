# Smooth TypeScript SDK

The Smooth TypeScript SDK provides a convenient way to interact with the Smooth API for programmatic browser automation and task execution.

## Features

*   **Task Management**: Easily run tasks and retrieve results upon completion.
*   **Session-Based Browsing**: Use the `session()` method to open a browser and run multiple tasks within the same context.
*   **Direct Browser Control**: Navigate, extract data, and execute JavaScript directly in the browser using `goto()`, `extract()`, and `evaluate_js()`.
*   **Custom Tools**: Register custom tools that can be called by the AI agent during task execution.
*   **Advanced Task Configuration**: Customize task execution with options for device type, session recording, stealth mode, and proxy settings.

## Installation

You can install the Smooth TypeScript SDK as follows:

```bash
npm install @circlemind-ai/smooth-ts
```

## Usage

This SDK mirrors the interface of the [Smooth Python SDK](https://docs.smooth.sh/quickstart), so refer to its documentation for additional details.

### Quick Start

Submit a task in seconds:

```typescript
import { SmoothClient } from "@circlemind-ai/smooth-ts";

const client = new SmoothClient({
  api_key: process.env.CIRCLEMIND_API_KEY,
});

const task = await client.run({
  task: "Go to google flights and find the cheapest flight from London to Paris today",
});

console.log("Live URL:", await task.live_url());
console.log("Agent response:", (await task.result()).output);
```

### Using Sessions

Sessions allow you to open a browser and run multiple tasks within the same context:

```typescript
import { SmoothClient } from "@circlemind-ai/smooth-ts";

const client = new SmoothClient();

// Open a session
const session = await client.session({ device: "desktop" });

// Use the session with the `use` method (similar to Python's context manager)
await session.use(async (s) => {
  // Navigate to a URL
  await s.goto("https://example.com");

  // Run a task
  const result = await s.run_task("Find the main heading on this page");
  console.log("Task result:", result.output);

  // Extract data
  const data = await s.extract({
    type: "object",
    properties: {
      title: { type: "string" },
    },
  });
  console.log("Extracted data:", data.data);

  // Execute JavaScript
  const jsResult = await s.evaluate_js("document.title");
  console.log("Page title:", jsResult.result);
});
```

### Direct Browser Control

You can interact with the browser directly using TaskHandle or SessionHandle:

```typescript
import { SmoothClient } from "@circlemind-ai/smooth-ts";

const client = new SmoothClient();
const task = await client.run({ task: "Go to https://news.ycombinator.com" });

// Wait for task to be ready, then interact with the browser
console.log("Live URL:", await task.live_url());

// Navigate to a different URL
await task.goto("https://example.com");

// Extract structured data
const extracted = await task.extract({
  type: "object",
  properties: {
    heading: { type: "string", description: "The main heading" },
  },
});
console.log("Extracted:", extracted.data);

// Execute JavaScript
const result = await task.evaluate_js("document.querySelectorAll('a').length");
console.log("Number of links:", result.result);

// Get the final result
const finalResult = await task.result();
console.log("Final output:", finalResult.output);
```

### Custom Tools

Register custom tools that the AI agent can call during task execution:

```typescript
import { SmoothClient, SmoothTool } from "@circlemind-ai/smooth-ts";

const client = new SmoothClient();

// Create a custom tool
const myTool = new SmoothTool({
  signature: {
    name: "get_weather",
    description: "Gets the current weather for a location",
    inputs: {
      location: { type: "string", description: "The city name" },
    },
    output: "The current weather information",
  },
  fn: async (task, { location }) => {
    // Your custom logic here
    return `Weather in ${location}: Sunny, 72°F`;
  },
  essential: true,
});

// Or use the decorator-style API
const anotherTool = client.tool(
  "calculate",
  "Performs a calculation",
  { expression: { type: "string" } },
  "The result of the calculation"
)((task, { expression }) => {
  return eval(expression);
});

// Use the tools in a task
const task = await client.run({
  task: "What's the weather in San Francisco?",
  custom_tools: [myTool, anotherTool],
});

const result = await task.result();
console.log(result.output);
```

### Profile Management

Manage browser profiles to maintain state between sessions:

```typescript
import { SmoothClient } from "@circlemind-ai/smooth-ts";

const client = new SmoothClient();

// Create a new profile
const profile = await client.create_profile();
console.log("Profile ID:", profile.id);

// List all profiles
const profiles = await client.list_profiles();
console.log("All profiles:", profiles);

// Use a profile in a session
const session = await client.session({
  profile_id: profile.id,
});

// Delete a profile
await client.delete_profile(profile.id);
```

## API Reference

### SmoothClient

- `run(options: RunTaskOptions): Promise<TaskHandle>` - Runs a task and returns a handle
- `session(options?: SessionOptions): Promise<SessionHandle>` - Opens a browser session
- `tool(name, description, inputs, output, essential?, error_message?): (fn) => SmoothTool` - Creates a custom tool
- `create_profile(profile_id?): Promise<ProfileResponse>` - Creates a browser profile
- `list_profiles(): Promise<ProfileResponse[]>` - Lists all profiles
- `delete_profile(profile_id): Promise<void>` - Deletes a profile
- `upload_file(file, name, purpose?): Promise<UploadFileResponse>` - Uploads a file
- `delete_file(file_id): Promise<void>` - Deletes a file
- `upload_extension(file, name): Promise<UploadExtensionResponse>` - Uploads an extension
- `list_extensions(): Promise<ListExtensionsResponse>` - Lists all extensions
- `delete_extension(extension_id): Promise<void>` - Deletes an extension

### TaskHandle

- `id(): string` - Returns the task ID
- `result(timeout?): Promise<TaskResponse>` - Waits for and returns the result
- `live_url(interactive?, embed?, timeout?): Promise<string>` - Returns the live URL
- `recording_url(timeout?): Promise<string>` - Returns the recording URL
- `downloads_url(timeout?): Promise<string>` - Returns the downloads URL
- `goto(url): Promise<ActionGotoResponse>` - Navigates to a URL
- `extract(schema, prompt?): Promise<ActionExtractResponse>` - Extracts data
- `evaluate_js(code, args?): Promise<ActionEvaluateJSResponse>` - Executes JavaScript

### SessionHandle (extends TaskHandle)

- `use<T>(callback): Promise<T>` - Executes a callback within the session context
- `close(force?): Promise<void>` - Closes the session
- `run_task(task, max_steps?, response_model?, url?, metadata?): Promise<ActionRunTaskResponse>` - Runs a task within the session

### SmoothTool

- `name: string` - The tool name
- `signature: ToolSignature` - The tool signature

## Deprecations

The following methods and options are deprecated:

- `open_session()` - Use `session()` instead
- `close_session()` - Sessions are now closed via `SessionHandle.close()`
- `list_sessions()` - Use `list_profiles()` instead
- `delete_session()` - Use `delete_profile()` instead
- `session_id` option - Use `profile_id` instead
- `exec_js()` - Use `evaluate_js()` instead
- `stop()` on TaskHandle - Deprecated