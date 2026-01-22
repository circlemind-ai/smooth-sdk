# Custom Tools Guide for Smooth TypeScript SDK

This guide explains how to create and use custom tools with the Smooth TypeScript SDK, enabling you to extend the agent's capabilities with custom functionality.

## Overview

Custom tools allow you to provide functions that the AI agent can call during task execution. This is useful for:
- Integrating with external APIs
- Accessing databases or internal systems
- Performing calculations or data transformations
- Any custom logic your agent needs to complete tasks

## Basic Usage

### Creating a Tool Directly

```typescript
import { SmoothClient, SmoothTool, ToolCallError, TaskHandle, SessionHandle } from '@circlemind-ai/smooth-ts';

const client = new SmoothClient();

const weatherTool = new SmoothTool({
  signature: {
    name: 'get_weather',
    description: 'Get the current weather for a given city',
    inputs: {
      city: {
        type: 'string',
        description: 'The name of the city',
      },
    },
    output: 'Weather information for the city',
  },
  fn: async (task: TaskHandle | SessionHandle, args: Record<string, any>) => {
    // Your implementation
    const response = await fetch(`https://api.weather.com/${args.city}`);
    return await response.json();
  },
});
```

### Using the Tool Decorator Pattern

```typescript
const calculatorTool = client.tool(
  'calculate',
  'Perform a mathematical calculation',
  {
    expression: {
      type: 'string',
      description: 'Mathematical expression to evaluate',
    },
  },
  'The result of the calculation'
)((task: TaskHandle | SessionHandle, args: Record<string, any>) => {
  return { result: evaluateExpression(args.expression) };
});
```

### Running Tasks with Custom Tools

```typescript
const taskHandle = await client.run({
  task: 'What is the weather in San Francisco?',
  custom_tools: [weatherTool, calculatorTool],
  device: 'desktop',
});

const result = await taskHandle.result();
console.log(result.output);
```

### Using Tools in Sessions

```typescript
const session = await client.session({
  custom_tools: [weatherTool],
  device: 'desktop',
});

await session.use(async (s) => {
  // Navigate and run tasks with access to custom tools
  await s.goto('https://example.com');
  const result = await s.run_task('Check the weather for my city');
  console.log(result.output);
});
```

## Tool Configuration

### SmoothToolOptions

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `signature` | `ToolSignature` | Yes | The tool's signature defining name, description, inputs, and output |
| `fn` | `ToolFunction` | Yes | The function to execute when the tool is called |
| `essential` | `boolean` | No | If true (default), errors propagate. If false, errors are caught and returned |
| `error_message` | `string` | No | Custom error message to return on failure (instead of actual error) |

### ToolSignature

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `name` | `string` | Yes | Unique name for the tool |
| `description` | `string` | Yes | Brief description of what the tool does |
| `inputs` | `Record<string, any>` | Yes | JSON schema describing the input parameters |
| `output` | `string` | Yes | Description of what the tool returns |

## Error Handling

### ToolCallError

Use `ToolCallError` to indicate user errors (invalid input, etc.). These result in a 400 status code:

```typescript
import { ToolCallError, TaskHandle, SessionHandle } from '@circlemind-ai/smooth-ts';

const tool = new SmoothTool({
  signature: {
    name: 'divide',
    description: 'Divide two numbers',
    inputs: {
      numerator: { type: 'number' },
      denominator: { type: 'number' },
    },
    output: 'The result of the division',
  },
  fn: (task: TaskHandle | SessionHandle, args: Record<string, any>) => {
    if (args.denominator === 0) {
      throw new ToolCallError('Cannot divide by zero');
    }
    return { result: args.numerator / args.denominator };
  },
});
```

### Essential vs Non-Essential Tools

**Essential tools** (default):
- Errors are propagated to the caller
- Task execution may be interrupted
- Status code: 500 for system errors

**Non-essential tools**:
- Errors are caught and sent back to the agent
- Task execution continues
- Status code: 400 for all errors

```typescript
const nonEssentialTool = new SmoothTool({
  signature: {
    name: 'optional_feature',
    description: 'An optional feature',
    inputs: { /* ... */ },
    output: 'Feature result',
  },
  essential: false, // Errors won't stop execution
  error_message: 'This feature is currently unavailable',
  fn: async (task, args) => {
    // Implementation
  },
});
```

## Accessing Task/Session from Tools

The tool function receives the `TaskHandle` or `SessionHandle` as its first argument, allowing you to interact with the browser directly:

```typescript
const interactiveTool = new SmoothTool({
  signature: {
    name: 'get_page_title',
    description: 'Get the current page title',
    inputs: {},
    output: 'The page title',
  },
  fn: async (task: TaskHandle | SessionHandle, args: Record<string, any>) => {
    // Use task handle to interact with the browser
    const result = await task.evaluate_js('document.title');
    return { title: result.result };
  },
});
```

## Advanced Features

### Async Functions

Tools support both synchronous and asynchronous functions:

```typescript
const asyncTool = new SmoothTool({
  signature: {
    name: 'fetch_data',
    description: 'Fetch data from an API',
    inputs: { url: { type: 'string' } },
    output: 'API response',
  },
  fn: async (task: TaskHandle | SessionHandle, args: Record<string, any>) => {
    const response = await fetch(args.url);
    return await response.json();
  },
});
```

### Using Tools with Direct Tool Signatures

You can also pass tool signatures directly (without the function) if you want to handle tool calls manually:

```typescript
const taskHandle = await client.run({
  task: 'Use my custom tool',
  custom_tools: [
    {
      name: 'my_tool',
      description: 'A custom tool',
      inputs: { param: { type: 'string' } },
      output: 'Result',
    },
  ],
});

// Note: When using ToolSignature directly, tool calls won't be automatically handled
```

## Response Size Limits

Tool responses are limited to approximately 64KB. If your response exceeds this:

```typescript
const largeTool = new SmoothTool({
  signature: {
    name: 'large_data',
    description: 'Fetch large dataset',
    inputs: { /* ... */ },
    output: 'Data summary',
  },
  fn: async (task, args) => {
    const largeData = await fetchLargeDataset();
    // Return a summary instead of the full data
    return {
      count: largeData.length,
      summary: largeData.slice(0, 100), // First 100 items
    };
  },
});
```

## Complete Example

```typescript
import { SmoothClient, SmoothTool, ToolCallError, TaskHandle, SessionHandle } from '@circlemind-ai/smooth-ts';

async function main() {
  const client = new SmoothClient({
    api_key: process.env.CIRCLEMIND_API_KEY,
  });

  // Define a custom database query tool
  const dbTool = new SmoothTool({
    signature: {
      name: 'query_database',
      description: 'Query the customer database',
      inputs: {
        query: {
          type: 'string',
          description: 'SQL query to execute',
        },
      },
      output: 'Query results',
    },
    essential: true,
    fn: async (task: TaskHandle | SessionHandle, args: Record<string, any>) => {
      // Validate input
      if (!args.query.toLowerCase().startsWith('select')) {
        throw new ToolCallError('Only SELECT queries are allowed');
      }
      
      // Execute query
      const results = await db.query(args.query);
      return { rows: results, count: results.length };
    },
  });

  // Run a task with the custom tool
  const taskResult = await client.run({
    task: 'Find all customers who made purchases in the last 30 days',
    custom_tools: [dbTool],
    max_steps: 10,
  });

  const result = await taskResult.result(300); // 5 minute timeout
  console.log('Task completed:', result.output);
  
  await client.close();
}

main().catch(console.error);
```

## Best Practices

1. **Clear Descriptions**: Provide clear, detailed descriptions for tools and their inputs
2. **Input Validation**: Always validate inputs before processing
3. **Error Handling**: Use `ToolCallError` for user errors, let system errors propagate
4. **Response Size**: Keep responses under 64KB; return summaries for large datasets
5. **Async Operations**: Use async functions for I/O operations
6. **Security**: Validate and sanitize all inputs to prevent injection attacks
7. **Essential Flag**: Set `essential: false` for optional features that shouldn't stop execution
8. **Task Access**: Leverage the `task` parameter to interact with the browser when needed

## TypeScript Types

```typescript
export interface ToolSignature {
  name: string;
  description: string;
  inputs: Record<string, any>;
  output: string;
}

export interface SmoothToolOptions {
  signature: ToolSignature;
  fn: ToolFunction;
  essential?: boolean;
  error_message?: string | null;
}

export type ToolFunction = (
  task: TaskHandle | SessionHandle,
  ...args: any[]
) => any | Promise<any>;

// Task event types (used internally)
export interface TaskEvent {
  name: string;
  payload: Record<string, any>;
  id?: string;
  timestamp?: number;
}

export interface TaskEventResponse {
  id: string;
}
```
