# Smooth - Browser for AI Agents

![Comparison](https://www.smooth.sh/images/comparison.gif)

**TL;DR:** Smooth is a browser for AI agents, enabling tools like Claude Code to navigate the web quickly, cheaply, and reliably. It can use your IP address to avoid captchas.

[Demo](https://docs.smooth.sh) · [Documentation](https://docs.smooth.sh) · [Get API Key](https://app.smooth.sh)

---

## Why Smooth?

Autonomous agents like Claude Code are amazing at meaningful work—but they're mostly stuck in the CLI. Meanwhile, most valuable human work happens in the browser.

Current browser tools (Playwright MCP, `--chrome` flags, etc.) operate at the wrong abstraction level. They expose hundreds of low-level actions—click, type, select—forcing large models to think about mechanics instead of goals.

This creates three problems:

1. **Cost & Latency** — Using a massive model for button clicks is expensive and slow
2. **Context Pollution** — Every click pollutes the context window, degrading performance on actual tasks
3. **Lack of Expertise** — General-purpose models aren't web navigation experts

Smooth solves this with a higher-level interface designed for how agents actually think: natural language and goals, not DOM manipulation.

**Today, Smooth is 20x faster and 5x cheaper than Claude Code with `--chrome`.**

---

## Table of Contents

- [CLI](#cli)
- [Python SDK](#python-sdk)
- [Authentication](#authentication)

---

## CLI

The Smooth CLI lets AI agents browse the web through simple commands.

```bash
pip install smooth-py
smooth config --api-key <your-key>
```

**Full CLI documentation:** [docs.smooth.sh/cli](https://docs.smooth.sh/cli)

### Quick Example

```bash
# Start a session
smooth start-session --url "https://example.com"

# Run a task
smooth run <session-id> "Find the pricing page and extract all plan names and prices"

# Close when done
smooth close-session <session-id>
```

---

## Python SDK

Use Smooth programmatically in your Python applications.

```bash
pip install smooth-py
```

**Full SDK documentation:** [docs.smooth.sh/sdk](https://docs.smooth.sh/sdk)

### Quick Example

```python
from smooth import SmoothClient

with SmoothClient(api_key="your-api-key") as client:
    task = client.run(
        task="Go to Hacker News and get the top 5 story titles",
        device="desktop"
    )
    result = task.result()
    print(result.output)
```

### Async Support

```python
import asyncio
from smooth import SmoothAsyncClient

async def main():
    async with SmoothAsyncClient() as client:
        task = await client.run(task="Search for 'AI agents' on Google")
        result = await task.result()
        print(result.output)

asyncio.run(main())
```

---

## Authentication

Get your API key at [app.smooth.sh](https://app.smooth.sh)

**Option 1: Environment variable**
```bash
export CIRCLEMIND_API_KEY="your-api-key"
```

**Option 2: Direct configuration**
```python
client = SmoothClient(api_key="your-api-key")
```

**Option 3: CLI config**
```bash
smooth config --api-key <your-key>
```

---

## Links

- [Documentation](https://docs.smooth.sh)
- [CLI Guide](https://docs.smooth.sh/cli)
- [SDK Reference](https://docs.smooth.sh/sdk)
- [Get API Key](https://app.smooth.sh)
