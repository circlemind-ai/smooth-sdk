---
name: smooth-sdk
description: >
  Python SDK for Smooth, an AI browser automation framework. Use when you need to implement
  features that require navigating sites, filling forms, logging in, 
  scraping/extracting structured web data, downloading files,
  automating multi-step web workflows, or running browser tasks at scale.
  Act as a consultant: scope the requirements, confirm a plan before coding (asking questions only
  where a decision needs the engineer's input), implement a best-practice automation, and iterate
  using the run artifacts (session log, recording, HAR, console log).
---

# Smooth Python SDK

Smooth offers serverless browsers infra and autonomous browser agents in cloud sandboxes. 
The agents take **tasks** in natural language and drive the browser autonomously to complete them. 
You orchestrate automation and resources from Python via `smooth`.

```bash
pip install smooth-py
```

```python
from smooth import SmoothClient
client = SmoothClient(api_key="cmzr-...")          # or set env SMOOTH_API_KEY
task = client.run("Find the cheapest flight from London to Paris today on Google Flights")
print(task.live_url())        # watch it live
print(task.result().output)   # blocks until done
```

Auth: pass `api_key=`, or set `SMOOTH_API_KEY`. Get a key at https://app.smooth.sh.
A TypeScript SDK (`@smooth-sh/smooth-ts`) is also available. It uses camelCase names such as `apiKey` and `task.liveUrl()`.

## Operating mode: act as a Smooth automation consultant

When an engineer asks you to build a Smooth automation, act as a **consultant, not a code
dispenser**. Work in this order:

1. **Understand & scope.** Pin down: the goal; target site(s); whether the flow is stable and
   recurring or novel each run; the exact input/output shape (→ `response_model`); auth needs;
   volume/concurrency; where and how it runs (one-off, service, schedule); data sensitivity.
2. **Ask only where a decision needs the engineer.** Resolve what you can from context and sensible
   defaults — don't interrogate. Do ask when a choice materially changes the design or carries a
   trade-off the engineer must own (see Authentication below).
3. **Always confirm a plan before writing code.** Lay out the intended design — primitives
   (default: one session with the goal split into `run_task` subtasks), task altitude (goal vs.
   step-hints), schemas, auth path, anti-bot/proxy posture — and get agreement first.
4. **Implement** per the reference below, best-practices by default: structured output on every
   task, least-privilege `allowed_urls`, secrets over hard-coded credentials, subtask
   decomposition for reliability.
5. **Validate and iterate — never declare done from a single happy-path run.** Run a small sample,
   inspect the run artifacts (see *Inspecting results*) to find where it broke, adjust, re-run. Use
   a profile during iteration to avoid re-authenticating each run.

**Authentication — explain the trade-off, let the engineer choose:**
- **Secrets are usually the best default.** Credentials are injected into the page at runtime,
  URL-scoped, and never exposed to the agent, logs, or traces. Proactively reassure the engineer of
  these guarantees — the real concern is usually "will the model see my password?", and it won't.
- **Profiles** suit durable logins (authenticate once, reuse) — but plan a path for the agent to
  **request a human to re-authenticate** (surface `live_url()`) when cookies expire.
- For **OTP / 2FA / SSO**, add a **custom tool** that fetches the code or drives the step.

## Writing tasks: goals vs. workflows

Smooth is a smart agent — how much you spell out depends on the job:

- **Novel / varying sites each run → give a goal.** Let the agent figure out the flow.
  - ✅ `"Search Amazon for 'wireless headphones', filter to 4+ stars, return the top 3 with prices"`
  - ❌ `"Click search box, type headphones, click submit, scroll 500px, click first result"` (too granular)
  - ❌ `"Find engineers who'd be a good fit for us"` (too vague — *you* decompose big goals into concrete tasks)
- **Same recurring flow every time → you may add high-level step hints** (a workflow), never granular
  clicks, and always tell the agent the site may have changed so it adapts rather than follows blindly:

  ```
  Goal: buy an iPhone 17 128GB on Amazon

  Here are high-level notes on how to do it. The website may have changed and the flow could differ:
  - go to amazon
  - search "iphone 17 128gb"
  - locate the right item and open its page
  - add it to cart
  - go to the basket
  - check out
  ```

- **When writing tasks, DO NOT guess steps that weren't given by the user.** — it only follows steps when *you* supply them.
- Start at a **base URL**; let the agent apply filters through the UI. Avoid `?filter=xyz` query params.

## Choosing the right primitive

| You need… | Use | Notes |
|---|---|---|
| One autonomous task, done | `client.run(task)` | Fire-and-forget; returns a `TaskHandle`. |
| Do several sequential things on one browser | `client.session()` | Run many actions/tasks, then close. Cross-run state → use a **profile**. |
| An agentic step inside a session | `session.run_task(task)` | LLM-driven; navigates/interacts/reasons. |
| Deterministic data pull (no agent steps, cheap) | `session.extract(schema, prompt)` | "Smart fetch" from the current/target page. |
| Deterministic navigation | `session.goto(url)` | Just loads the URL. |
| Raw JS in the page | `session.evaluate_js(code, args)` | Full control; returns the JS value. |
| Run tasks in parallel | **separate** sessions, async client | One browser = one task at a time; parallelize across sessions. |

`run` vs `session`: **prefer sessions.** `client.run(task)` is essentially syntactic sugar for a
session that does one `run_task` and auto-closes. A `session` lets you drive one browser across many
sequential steps (`goto`/`extract`/`run_task`/`evaluate_js`), and — most importantly — lets you
**split a big task into smaller subtasks**, each its own `run_task`. That decomposition is a good
reliability pattern for long-horizon or highly repetitive tasks: smaller, well-scoped tasks succeed far more often than one sprawling goal.
The browser's state (cookies, URL, open page) persists across steps, but the agent's **memory does
not carry** between `run_task` calls — pass needed context in each prompt. For state that must
survive *across* sessions (logins), use a **profile**.

## Core API

### `client.run(...) -> TaskHandle`
```python
handle = client.run(
    task="...",                 # the goal (natural language)
    response_model=MyModel,     # Pydantic class OR JSON-schema dict -> structured output
    url="https://...",          # optional starting URL (else agent infers)
    metadata={"city": "SF"},    # plain variables visible to the agent (referenced by name in task)
    max_steps=32,               # agent step budget, 2..128
    device="desktop",           # "desktop" (default) | "mobile"
    profile_id="my-login",      # reuse a saved profile (cookies/logins)
    allowed_urls=["https://**.example.com/**"],   # glob allowlist; None = all
    files=[file_id],            # uploaded file ids the agent can use
    custom_tools=[my_tool],     # functions the agent can call
    additional_tools={"screenshot": None},        # enable built-in tools
    extensions=[ext_id],        # browser extensions to load
)
resp = handle.result(timeout=300)   # blocks; raises TimeoutError if exceeded
resp.output          # the result (str, or an instance/dict of response_model)
resp.status          # "done" | "failed" | "cancelled" | ...
resp.credits_used
handle.live_url()        # interactive live-view URL (while running)
handle.recording_url()   # video (needs enable_recording=True, default True) — call after completion
handle.downloads_url()   # zip of files the task downloaded — call after completion
```
**Almost always pass `response_model`** (a Pydantic class or JSON-schema dict). Free-text `output`
is rarely the right shape to consume in code — the same reason you use structured outputs when
coding against any LLM. Without it, `output` is a plain string.

### `client.session(...) -> SessionHandle`
```python
with client.session(device="desktop", profile_id="my-login") as session:
    session.goto("https://books.toscrape.com")
    books = session.extract(Books.model_json_schema(), prompt="Extract all books with prices")
    # books.output -> data matching the schema
    r = session.run_task("Open the first Mystery book's detail page")
    title = session.evaluate_js("document.querySelector('h1').textContent")
# leaving the block closes the session (persists state only if a profile_id was set)
```
- `session(**kwargs)` accepts the same config as `run` (except `task`), plus `proxy_server="self"`.
- `session.extract(schema, prompt=None)` — `schema` is a JSON-schema dict; returns `.output`.
- `session.run_task(task, max_steps=32, response_model=None, url=None, metadata=None, secrets=None)`.
- `session.evaluate_js(code, args=None)` — `code` runs as-is, or as an arrow fn `(args) => ...`
  when you pass `args` (a dict). Returns `.output`.
- `session.close(force=True)`; `session.result()` returns the final trace — **only after close**.
- Call `recording_url()` / `downloads_url()` **after** the session closes (or the task completes);
  calling them mid-run can deadlock.

### Async
Everything mirrors under `SmoothAsyncClient`; `await` every call. Sessions support both forms:
```python
from smooth import SmoothAsyncClient
async with SmoothAsyncClient() as client:
    handle = await client.run("...")
    resp = await handle.result(timeout=120)

    async with client.session() as session:      # or: session = await client.session()
        await session.goto("https://example.com")
        r = await session.evaluate_js("document.title")
```
For **parallelism**, open several independent sessions and drive them concurrently with
`asyncio.gather` — a single session/browser still runs only one task at a time.

## Features

### Structured output
Pass `response_model` (Pydantic class or JSON schema) on nearly every task — the agent returns data matching it, ready to consume in code.
```python
from pydantic import BaseModel, Field
class Product(BaseModel):
    name: str; price: float | None = Field(None); url: str
class Products(BaseModel):
    products: list[Product]
out = client.run("Extract page-1 Amazon results for 'playstation'",
                 url="https://www.amazon.com", response_model=Products).result().output
```

### Profiles (persistent auth)
A profile stores cookies/localStorage/logins. Reuse it to stay logged in.
```python
client.create_profile(profile_id="github")     # create a named profile
# Log in once (headful): open session, goto login, hand user the live_url to authenticate,
# then close to persist. Later just reuse:
client.run("Create an issue in my repo", profile_id="github")
```
- `profile_read_only=True` loads a profile without saving changes back.
- Manage: `create_profile`, `list_profiles`, `delete_profile`. Track which profile ↔ which site.

### Files (upload / download)
```python
with open("doc.pdf", "rb") as f:
    fid = client.upload_file(f, purpose="contract to analyze").id
client.run("Analyze the uploaded contract", files=[fid])
# Downloads the task made -> handle.downloads_url() returns a zip; also delete_file(fid).
```

### Secrets (values the LLM must never see)
Unlike `metadata` (plain visible variables), `secrets` are injected into the page but redacted
from the agent, logs, and traces, and video recording. URL-scoped using glob-like syntax.
```python
from smooth import Secret
from pydantic import SecretStr
with client.session() as s:
    s.run_task(
        "Log in using the `password` value",
        url="https://example.com/login",
        secrets={"password": Secret(value=SecretStr("hunter2"),
                                    allowed_urls=["**.example.com/**"])},
    )
```
Reference a secret in the task by its key name. Only available on `session.run_task`.

### Authentication (two paths)
When a task needs a logged-in session, pick one:
- **Profiles** — authenticate once, reuse the profile on later runs while its cookies stay valid.
  Best for durable logins. Build in a way for the agent to **request a human to re-authenticate**
  (surface `live_url()` so a person can log in) when cookies expire.
- **Secrets** — inject credentials per-run with no persistence (see above). Best for one-offs or
  when you don't want to store a profile. Pair with a custom tool to handle **OTP / 2FA**.

### Custom tools
Expose Python functions the agent can call (APIs, DBs, computed values).
```python
@client.tool(
    name="get_quote", description="Fetch a shipping quote",
    inputs={"zip": {"type": "string", "description": "destination ZIP"}},
    output="quote in USD",
    essential=True,          # essential error -> fails task; non-essential -> agent sees error, continues
)
def get_quote(zip: str):     # first param named `task` (optional) receives the handle
    if not zip.isdigit():
        raise ToolCallError("ZIP must be numeric")   # user-facing 400 back to the agent
    return {"usd": 12.5}

client.run("Quote shipping to 94107 using get_quote", custom_tools=[get_quote])
```
- Sync fn with `SmoothClient`; `async def` with `SmoothAsyncClient`.
- A `task`-named first arg gives the tool the handle → `task.evaluate_js(...)`, or `task.run_task(...)`
  to spawn a **sub-agent** sharing the browser (max nesting depth 2; no two concurrent `run_task`
  in one session). Tool return must be JSON-serializable and <~64KB (return summaries for big data).

Custom tools are the main extensibility lever. A tool is just **arbitrary code running in your own
environment** — it can do literally anything you can do in Python:
- **Integrate anything**: call MCP servers, external services, internal APIs, databases.
- **`ask_human`**: give the agent an escape hatch to reach a person — send a Slack message, page
  someone, open a ticket — and return their answer to the agent.
- **OTP / 2FA**: fetch the code from your inbox/API and hand it back to the agent.
- **Arbitrary browser ops** via `task.evaluate_js(...)` (raw CDP coming soon).
- **Context hygiene for auth/payments**: wrap a sensitive flow in a tool that runs a **subtask**
  (`task.run_task(...)`) to verify it's safe to authenticate/pay *before* proceeding, keeping that
  reasoning out of the main agent's context. (See the nested-`run_task` e2e test for the pattern.)

### Built-in extra tools (`additional_tools`)
Map tool name → config dict (or `None` for defaults):
```python
additional_tools={
    "screenshot": {"full_page": True},
    "hover": None,
    "drag_drop": None,
    "print_page": {"print_and_screenshot": True, "print_background": True},  # -> PDF in downloads zip
}
```

### Browser extensions
```python
with open("ext.zip", "rb") as f:
    eid = client.upload_extension(f).id
client.run("...", extensions=[eid])            # list_extensions(), delete_extension(eid)
```

### Proxies
- External: `proxy_server=..., proxy_username=..., proxy_password=...` (e.g. residential/geo-routed).
- **`proxy_server="self"`** (sessions only): routes the sandbox browser through *your* machine via a
  P2P tunnel — useful to appear from your own IP / reach intranet.
```python
with client.session(proxy_server="self") as s:
    s.run_task("What's my IP?", url="https://whatismyipaddress.com/")
```

### Anti-bot / detection
For sites with bot detection:
- Keep `use_stealth=True` (default) and add `experimental_features={"humanize": True}` for
  human-like interaction timing.
- If still blocked, escalate proxies in order: **no proxy → ISP → residential**.

### Other options
- `device`: `"mobile"` / `"desktop"` (default)
- `use_stealth=True` (default) anti-bot stealth; `use_adblock=True`; `use_captcha_solver=True`.
- `allowed_urls`: glob allowlist on domain+path, e.g. `["https://**.example.com/**"]`. None = all.
- `enable_recording=True` → `recording_url()`. `show_cursor=False`.
- `certificates=[{"file": open("c.p12","rb"), "password": "..."}]` for mTLS sites.
- `experimental_features={"enhanced_vision": None}` — opt-in experimental behaviors (see Anti-bot for `humanize`).
- `metadata` values are `str|int|float|bool`, referenced by name in the task text.

### Inspecting results (for debugging & iteration)
A completed task/session carries more than `output`. Use these to see what happened and iterate
(all work on `TaskHandle` and `SessionHandle`; for sessions, read them after `close()`):
- `handle.session_log()` — timestamped steps the agent took (where it went wrong).
- `handle.recording_url()` — video of the run.
- `handle.har_url()` — network HAR (blocked requests, CORS, proxy, API calls).
- `handle.console_log_url()` — browser console (page JS errors).
- `handle.live_url()` — watch live / intervene while running.

Artifacts are written on completion — poll briefly if not yet ready.

## Errors & gotchas
- Exceptions: `ApiError`, `BadRequestError`, `ToolCallError`, `TimeoutError` (all from `smooth`).
- `result(timeout=...)` raises `TimeoutError` past the deadline; `timeout=None` waits indefinitely.
- One task per session at a time; parallelism = many sessions (async + `gather` pattern).
- `session.result()` works only after the session is closed (use `client.run` for one-shots).
- Closing a session persists profile state; give it a moment before reusing the profile elsewhere.
- Deprecated (avoid): `session_id`→`profile_id`, `stealth_mode`→`use_stealth`, `exec_js`→`evaluate_js`,
  `open_session`/`close_session`/`list_sessions`/`delete_session` (use `session()`/profile methods),
  `TaskHandle.stop()`/`update()`.
- Out of credits → the API errors; upgrade at https://app.smooth.sh.

Docs: https://docs.smooth.sh · Quickstart: https://docs.smooth.sh/quickstart
