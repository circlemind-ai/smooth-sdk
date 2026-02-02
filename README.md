# Smooth - Browser automation for AI

![Comparison](https://www.smooth.sh/images/comparison.gif)

**TL;DR:** Smooth is an AI browser automation SDK and CLI that can act and extract information from the web. It's powered by our browser agent which controls the browser with mouse and keyboard to carry out tasks autonomously on the web.

[Discord](https://discord.com/invite/VcdgMwUmMG) · [Documentation](https://docs.smooth.sh) · [Get API Key](https://app.smooth.sh)

---

## Table of Contents

- [CLI](#cli)
- [Python SDK](#python-sdk)

---

## CLI

The Smooth CLI is a browser for AI agents, enabling tools like Claude Code to navigate the web quickly, cheaply, and reliably. **It can use your IP address to avoid captchas.**

### Why Smooth?

Autonomous agents like Claude Code are amazing at meaningful work—but they're mostly stuck in the CLI. Meanwhile, most valuable human work happens in the browser.

Current browser tools (Playwright MCP, `--chrome` flags, etc.) operate at the wrong abstraction level. They expose hundreds of low-level actions—click, type, select—forcing large models to think about mechanics instead of goals.

This creates three problems:

1. **Cost & Latency** — Using a massive model for button clicks is expensive and slow
2. **Context Pollution** — Every click pollutes the context window, degrading performance on actual tasks
3. **Lack of Expertise** — General-purpose models aren't web navigation experts

Smooth solves this with a higher-level interface designed for how agents actually think: natural language and goals, not DOM manipulation.

**Today, Smooth is 20x faster and 5x cheaper than Claude Code with `--chrome`.**

Get your API key at [app.smooth.sh](https://app.smooth.sh) and then run:

```bash
pip install smooth-py
smooth config --api-key <your-key>
npx skills add https://github.com/circlemind-ai/smooth-sdk
```

**Full CLI documentation:** [docs.smooth.sh/cli](https://docs.smooth.sh/cli)

### How It Works

Instead of this:

```bash
click(x=342, y=128)
type("search query")
click(x=401, y=130)
scroll(down=500)
click(x=220, y=340)
... (50 more steps)
```

Your agent just says:

```bash
"Search for flights from NYC to LA and find the cheapest option"
```

The agent thinks about your goals. Smooth handles the browser.

### Quick Example

```bash
# Start a session
smooth start-session --url "https://example.com"

# Run a task
smooth run <session-id> "Find the pricing page and extract all plan names and prices"

# Close when done
smooth close-session <session-id>
```

**Pro Tip:** You can also give your agent complex goals. Our skill will teach your agent how to break them into subtasks and distribute them across multiple concurrent browser sessions automatically.

### Works With

- Claude Code
- Clawdbot / Moltbot / OpenClaw
- Codex
- Cursor
- Antigravity
- Cline
- Factory AI
- Github Copilot
- Kiro
- OpenCode
- Windsurf
- Any other agent that can run CLI commands

---

## Python SDK

Use our Smooth SDK to automate any digital work.

```bash
pip install smooth-py
```

**Full SDK documentation:** [docs.smooth.sh/sdk](https://docs.smooth.sh/sdk)

### Quick Example

```python
from smooth import SmoothClient

smooth_client = SmoothClient(api_key="cmzr-YOUR_API_KEY")
task = smooth_client.run("Go to google flights and find the cheapest flight from London to Paris today")

print(f"Live URL: {task.live_url()}")
print(f"Agent response: {task.result()}")
```

We have async clients, persistent sessions, auto-captcha solvers, stealth mode, infinite scaling, and much more. Dive deep in the docs, it's fun.

Smooth is **state-of-the-art on reliability, speed, and cost**, check out our performance summary: https://docs.smooth.sh/performance

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

- [Documentation & SDK](https://docs.smooth.sh)
- [CLI Guide](https://docs.smooth.sh/cli)
- [Get API Key](https://app.smooth.sh)
