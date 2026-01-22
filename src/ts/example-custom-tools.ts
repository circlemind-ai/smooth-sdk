/**
 * Example demonstrating custom tools usage with the Smooth TypeScript SDK
 */

import { SmoothClient, SmoothTool, ToolCallError, TaskHandle, SessionHandle } from './smooth';

async function main() {
  // Initialize the client
  const client = new SmoothClient({
    api_key: process.env.CIRCLEMIND_API_KEY,
  });

  // Example 1: Create a custom tool directly
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
      // Simulate API call
      console.log(`Fetching weather for ${args.city}...`);
      
      // Example: throw ToolCallError for user errors
      if (!args.city) {
        throw new ToolCallError('City name is required');
      }
      
      return {
        city: args.city,
        temperature: 72,
        condition: 'sunny',
        humidity: 45,
      };
    },
    essential: true, // If true, errors will propagate; if false, errors are caught
    error_message: 'Failed to fetch weather data', // Custom error message
  });

  // Example 2: Use the tool decorator pattern
  const calculatorTool = client.tool(
    'calculate',
    'Perform a mathematical calculation',
    {
      expression: {
        type: 'string',
        description: 'Mathematical expression to evaluate',
      },
    },
    'The result of the calculation',
    false // Non-essential tool - errors won't stop execution
  )((task: TaskHandle | SessionHandle, args: Record<string, any>) => {
    try {
      // WARNING: eval is dangerous - this is just for demonstration
      const result = eval(args.expression);
      return { result };
    } catch (error) {
      throw new ToolCallError('Invalid mathematical expression');
    }
  });

  // Run a task with custom tools
  const taskHandle = await client.run({
    task: 'What is the weather in San Francisco and what is 2+2?',
    custom_tools: [weatherTool, calculatorTool],
    device: 'desktop',
    max_steps: 10,
  });

  console.log('Task started:', taskHandle.id());

  // Wait for the task to complete
  // The SDK will automatically handle tool calls during execution
  try {
    const result = await taskHandle.result(300); // 5 minutes timeout
    console.log('Task completed!');
    console.log('Status:', result.status);
    console.log('Output:', result.output);
  } catch (error) {
    console.error('Task failed:', error);
  }

  // Clean up
  await client.close();
}

// Example demonstrating sessions
async function sessionExample() {
  const client = new SmoothClient();

  // Open a browser session
  const session = await client.session({
    device: 'desktop',
    profile_id: 'my-profile', // Optional: use a saved profile
  });

  // Use the session with the context manager pattern
  await session.use(async (s) => {
    // Navigate to a URL
    await s.goto('https://example.com');

    // Run a task within the session
    const taskResult = await s.run_task('Extract the page title');
    console.log('Task output:', taskResult.output);

    // Extract structured data
    const extracted = await s.extract({
      type: 'object',
      properties: {
        title: { type: 'string' },
        description: { type: 'string' },
      },
    });
    console.log('Extracted data:', extracted.data);

    // Execute JavaScript
    const jsResult = await s.evaluate_js('document.title');
    console.log('Page title:', jsResult.result);
  });

  await client.close();
}

// Run the examples
if (require.main === module) {
  main()
    .then(() => sessionExample())
    .catch(console.error);
}
