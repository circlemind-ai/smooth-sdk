---
name: smooth-browser
description: Browser automation for AI agents to carry out any task on the web. Use when you need to navigate websites, fill forms, take screenshots, extract web data, test web apps, or automate browser workflows. Trigger phrases include "go to [url]", "click on", "fill out the form", "take a screenshot", "scrape", "automate", "test the website", "log into", or any browser interaction request.
---

# Smooth Browser

A browser for AI agents interact with websites, authenticate, scrape data, and perform complex workflows.

## Prerequisites

Ensure the `CIRCLEMIND_API_KEY` environment variable is set before using any commands.

## Basic Workflow

### 1. Create a Profile (Optional)

Profiles are useful to persist cookies, login sessions, and browser state between sessions.

```bash
smooth create-profile --profile-id "my-profile"
```

List existing profiles:
```bash
smooth list-profiles
```

### 2. Start a Browser Session

```bash
smooth start-session --profile-id "my-profile" --url "https://example.com"
```

**Options:**
- `--profile-id` - Use a specific profile (optional, creates anonymous session if not provided)
- `--url` - Initial URL to navigate to (optional)
- `--files` - Comma-separated file IDs to make available in the session (optional)
- `--device mobile|desktop` - Device type (default: mobile)
- `--profile-read-only` - Load profile without saving changes
- `--allowed-urls` - Comma-separated URL patterns (e.g., "https://*example.com/*,https://*api.example.com/*")

**Important:** Save the session ID from the output - you'll need it for all subsequent commands.

**Defaults:** Sessions run in stealth mode with adblock enabled and no recording by default.

### 3. Run Tasks in the Session

Execute tasks using natural language:

```bash
smooth run <session-id> "Go to reddit.com and find the top 3 posts about AI"
```

**With structured output (for tasks requiring interaction):**
```bash
smooth run <session-id> "Search for 'wireless headphones', filter by 4+ stars, sort by price, and extract the top 3 results" \
  --url "https://shop.example.com" \
  --response-model '{"type":"object","properties":{"products":{"type":"array","items":{"type":"object","properties":{"name":{"type":"string"},"price":{"type":"number"},"rating":{"type":"number"}}}}}}'
```

**With metadata:**
```bash
smooth run <session-id> "Fill out the form with user information" \
  --metadata '{"email":"user@example.com","name":"John Doe"}'
```

**Options:**
- `--url` - Navigate to this URL before running the task
- `--metadata` - JSON object with variables for the task
- `--response-model` - JSON schema for structured output
- `--max-steps` - Maximum agent steps (default: 32)
- `--json` - Output results as JSON

### 4. Close the Session

```bash
smooth close-session <session-id>
```

**Important:** Wait 5 seconds after closing to ensure cookies and state are saved to the profile if you need it for another session.

---

## Common Use Cases

### Authentication & Persistent Sessions

**Create a profile for a specific website:**
```bash
# Create profile
smooth create-profile --profile-id "github-account"

# Start session
smooth start-session --profile-id "github-account" --url "https://github.com/login"

# Get live view to authenticate manually
smooth live-view <session-id>
# Give the URL to the user so it can open it in the browser and log in

# When the user confirms the login you can then close the session to save the profile data
smooth close-session <session-id>
# Save the profile-id somewhere to later reuse it
```

**Reuse authenticated profile:**
```bash
# Next time, just start a session with the same profile
smooth start-session --profile-id "github-account"
smooth run <session-id> "Create a new issue in my repo 'my-project'"
```

**Keep profiles organized:** Track which profiles authenticate to which services so you can reuse them efficiently.

---

### Sequential Tasks on Same Browser

Execute multiple tasks in sequence without closing the session:

```bash
SESSION_ID=$(smooth start-session --profile-id "my-profile" --json | jq -r .session_id)

# Task 1: Login
smooth run $SESSION_ID "Log into the website with the credentials in the form"

# Task 2: Navigate
smooth run $SESSION_ID "Go to the settings page"

# Task 3: Update
smooth run $SESSION_ID "Change the notification preferences to email only"

smooth close-session $SESSION_ID
```

**Important:** `run` preserves the browser state (cookies, URL, page content) but **not** the browser agent's memory. If you need to carry information from one task to the next, you should pass it explicitly in the prompt.

**Example - Passing context between tasks:**
```bash
# Task 1: Get information
RESULT=$(smooth run $SESSION_ID "Find the product name on this page" --json | jq -r .output)

# Task 2: Use information from Task 1
smooth run $SESSION_ID "Consider the product with name '$RESULT'. Now compare its price with similar products offered by this online store."
```

**Note:** Wait for each task to complete before starting the next. For parallel execution, create multiple sessions.

---

### Web Scraping with Structured Output

**Option 1: Using `run` with structured output:**

```bash
smooth start-session --url "https://news.ycombinator.com"
smooth run <session-id> "Extract the top 10 posts" \
  --response-model '{
    "type": "object",
    "properties": {
      "posts": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "title": {"type": "string"},
            "url": {"type": "string"},
            "points": {"type": "number"}
          }
        }
      }
    }
  }'
```

**Option 2: Using `extract` for direct data extraction:**

The `extract` command is more efficient for pure data extraction as it doesn't use agent steps:

```bash
smooth start-session
smooth extract <session-id> \
  --url "https://news.ycombinator.com" \
  --schema '{
    "type": "object",
    "properties": {
      "posts": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "title": {"type": "string"},
            "url": {"type": "string"},
            "points": {"type": "number"}
          }
        }
      }
    }
  }' \
  --prompt "Extract the top 10 posts"
```

**When to use each:**
- Use `extract` when you're on the right page and just need to pull structured data
- Use `run` when you need the agent to navigate, interact, or perform complex actions before extracting

---

### Working with Files

**Upload files for use in sessions:**

Files must be uploaded before starting a session, then passed to the session via file IDs:

```bash
# Step 1: Upload files
FILE_ID=$(smooth upload-file /path/to/document.pdf --purpose "Contract to analyze" --json | jq -r .file_id)

# Step 2: Start session with the file
smooth start-session --files "$FILE_ID" --url "https://example.com"

# Step 3: The agent can now access the file in tasks
smooth run <session-id> "Analyze the contract document and extract key terms"
```

**Upload multiple files:**
```bash
# Upload files
FILE_ID_1=$(smooth upload-file /path/to/invoice.pdf --json | jq -r .file_id)
FILE_ID_2=$(smooth upload-file /path/to/screenshot.png --json | jq -r .file_id)

# Start session with multiple files
smooth start-session --files "$FILE_ID_1,$FILE_ID_2"
```

**Download files from session:**
```bash
smooth run <session-id> "Download the monthly report PDF" --url
smooth close-session <session-id>

# After session closes, get download URL
smooth downloads <session-id>
# Visit the URL to download files
```

---

### Live View & Manual Intervention

When automation needs human input (CAPTCHA, 2FA, complex authentication):

```bash
smooth start-session --profile-id "my-profile"
smooth run <session-id> "Go to secure-site.com and log in"

# If task encounters CAPTCHA or requires manual action:
smooth live-view <session-id>
# Open the URL and complete the manual steps

# Continue automation after manual intervention:
smooth run <session-id> "Now navigate to the dashboard and export data"
```

---

### Direct Browser Actions

**Extract data from current page:**

```bash
smooth start-session --url "https://example.com/products"
smooth extract <session-id> \
  --schema '{"type":"object","properties":{"products":{"type":"array"}}}' \
  --prompt "Extract all product names and prices"
```

**Navigate to URL then extract:**

```bash
smooth extract <session-id> \
  --url "https://example.com/products" \
  --schema '{"type":"object","properties":{"products":{"type":"array"}}}'
```

**Execute JavaScript in the browser:**

```bash
# Simple JavaScript
smooth evaluate-js <session-id> "document.title"

# With arguments
smooth evaluate-js <session-id> "return args.x + args.y" \
  --args '{"x": 5, "y": 10}'

# Complex DOM manipulation
smooth evaluate-js <session-id> \
  "document.querySelectorAll('a').length"
```

---

## Profile Management

**List all profiles:**
```bash
smooth list-profiles
```

**Delete a profile:**
```bash
smooth delete-profile <profile-id>
```

**When to use profiles:**
- ✅ Websites requiring authentication
- ✅ Maintaining session state across multiple task runs
- ✅ Avoiding repeated logins
- ✅ Preserving cookies and local storage

**When to skip profiles:**
- Public websites that don't require authentication
- One-off scraping tasks
- Testing scenarios

---

## File Management

**Upload files:**
```bash
smooth upload-file /path/to/file.pdf --name "document.pdf" --purpose "Contract for review"
```

**Delete files:**
```bash
smooth delete-file <file-id>
```

---

## Proxy Support

Use a local proxy with public tunnel exposure for sessions that need to appear from your own network.

### Start a Proxy

**Important:** The proxy runs as a **blocking foreground process**. You must run it in a **background terminal** or use a terminal multiplexer (tmux/screen) to keep it running while you use other smooth commands.

```bash
# Start in a dedicated terminal (blocks until stopped with Ctrl+C)
smooth start-proxy
```

**Options:**
- `--provider cloudflare|serveo|microsoft` - Tunnel provider (default: cloudflare)
- `--port PORT` - Local port (default: 8888)
- `--timeout SECONDS` - Tunnel startup timeout (default: 30)
- `--verbose` - Enable verbose output

The command will block. **Keep this terminal open** while using the proxy.

**Example - Using with tmux:**
```bash
# Start proxy in background tmux session
tmux new-session -d -s smooth-proxy 'smooth start-proxy'

# Use smooth commands in your current terminal
smooth start-session --url "https://example.com"

# Stop proxy when done
tmux kill-session -t smooth-proxy
```

### Check Proxy Status

From any terminal, check if a proxy is running:

```bash
smooth proxy-status
```

This displays the proxy URL and credentials needed to connect.

### Stop the Proxy

Press `Ctrl+C` in the terminal where the proxy is running. The proxy state is cleaned up automatically.

### Automatic Proxy Usage

When a proxy is running, `smooth start-session` automatically discovers and uses it:

```bash
# Terminal 1: Start proxy (blocks)
smooth start-proxy

# Terminal 2: Sessions automatically use the proxy
smooth start-session --url "https://example.com"
# Output: "Using proxy: https://..."
```

## Best Practices

1. **Always save session IDs** - You'll need them for subsequent commands
2. **Use profiles for authenticated sessions** - Track which profile is for which website
3. **Wait 5 seconds after closing sessions** - Ensures state is properly saved
4. **Use descriptive profile IDs** - e.g., "linkedin-personal", "twitter-company"
5. **Close sessions when done** - Graceful close (default) ensures proper cleanup
6. **Use structured output for data extraction** - Provides clean, typed results
7. **Leverage live-view for debugging** - See what the agent sees in real-time
8. **Run sequential tasks in the same session** - More efficient than creating new sessions

---

## Troubleshooting

**"Session not found"** - The session may have timed out or been closed. Start a new one.

**"Profile not found"** - Check `smooth list-profiles` to see available profiles.

**CAPTCHA or authentication issues** - Use `smooth live-view <session-id>` to manually intervene.

**Task timeout** - Increase `--max-steps` or break the task into smaller steps.

---

## Command Reference

### Profile Commands
- `smooth create-profile [--profile-id ID]` - Create a new profile
- `smooth list-profiles` - List all profiles
- `smooth delete-profile <profile-id>` - Delete a profile

### File Commands
- `smooth upload-file <path> [--name NAME] [--purpose PURPOSE]` - Upload a file
- `smooth delete-file <file-id>` - Delete an uploaded file

### Session Commands
- `smooth start-session [OPTIONS]` - Start a browser session
- `smooth close-session <session-id> [--force]` - Close a session
- `smooth run <session-id> "<task>" [OPTIONS]` - Run a task
- `smooth extract <session-id> --schema SCHEMA [OPTIONS]` - Extract structured data
- `smooth evaluate-js <session-id> "code" [--args JSON]` - Execute JavaScript
- `smooth live-view <session-id>` - Get interactive live URL
- `smooth recording-url <session-id>` - Get recording URL
- `smooth downloads <session-id>` - Get downloads URL

### Proxy Commands
- `smooth start-proxy [OPTIONS]` - Start a local proxy with tunnel (blocking process)
- `smooth proxy-status` - Show proxy status and credentials

All commands support `--json` flag for JSON output.
