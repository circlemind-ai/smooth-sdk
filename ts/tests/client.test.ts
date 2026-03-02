import { describe, it, expect, beforeEach, vi } from "vitest";
import { SmoothClient } from "../src/client.js";
import { ApiError } from "../src/errors.js";
import { Telemetry } from "../src/telemetry.js";

const FAKE_KEY = "cmzr-test-key-0123456789abcdef";
const BASE = "https://api.smooth.sh/api/v1";

function mockFetch(
  responses: Array<{
    status?: number;
    body?: unknown;
    ok?: boolean;
    throwError?: Error;
  }>,
): typeof globalThis.fetch {
  let callIndex = 0;
  const calls: Array<{ url: string; init: RequestInit }> = [];

  const fn = async (
    input: string | URL | Request,
    init?: RequestInit,
  ): Promise<Response> => {
    const url = typeof input === "string" ? input : input.toString();
    calls.push({ url, init: init ?? {} });

    const spec = responses[Math.min(callIndex++, responses.length - 1)];

    if (spec.throwError) throw spec.throwError;

    const status = spec.status ?? 200;
    const ok = spec.ok ?? (status >= 200 && status < 300);
    const body = JSON.stringify(spec.body ?? {});

    return new Response(body, {
      status,
      statusText: ok ? "OK" : "Error",
      headers: { "Content-Type": "application/json" },
    });
  };

  (fn as { calls?: typeof calls }).calls = calls;
  return fn as typeof globalThis.fetch;
}

function getCalls(
  fetch: typeof globalThis.fetch,
): Array<{ url: string; init: RequestInit }> {
  return (fetch as { calls?: Array<{ url: string; init: RequestInit }> })
    .calls!;
}

beforeEach(() => {
  Telemetry.reset();
});

describe("SmoothClient constructor", () => {
  it("requires api key", () => {
    const oldKey = process.env.CIRCLEMIND_API_KEY;
    delete process.env.CIRCLEMIND_API_KEY;
    try {
      expect(() => new SmoothClient()).toThrow("API key is required");
    } finally {
      if (oldKey) process.env.CIRCLEMIND_API_KEY = oldKey;
    }
  });

  it("uses env var when no key provided", () => {
    const oldKey = process.env.CIRCLEMIND_API_KEY;
    process.env.CIRCLEMIND_API_KEY = FAKE_KEY;
    try {
      const client = new SmoothClient({ _fetch: mockFetch([]) });
      expect(client.apiKey).toBe(FAKE_KEY);
    } finally {
      if (oldKey) process.env.CIRCLEMIND_API_KEY = oldKey;
      else delete process.env.CIRCLEMIND_API_KEY;
    }
  });

  it("explicit key overrides env", () => {
    const client = new SmoothClient({
      apiKey: FAKE_KEY,
      _fetch: mockFetch([]),
    });
    expect(client.apiKey).toBe(FAKE_KEY);
  });

  it("constructs base url with version", () => {
    const client = new SmoothClient({
      apiKey: FAKE_KEY,
      baseUrl: "https://api.test.com/",
      apiVersion: "v2",
      _fetch: mockFetch([]),
    });
    expect(client.baseUrl).toBe("https://api.test.com/v2");
  });

  it("strips trailing slash from base url", () => {
    const client = new SmoothClient({
      apiKey: FAKE_KEY,
      baseUrl: "https://api.test.com/",
      _fetch: mockFetch([]),
    });
    expect(client.baseUrl).toBe("https://api.test.com/v1");
  });

  it("sets headers", () => {
    const client = new SmoothClient({
      apiKey: FAKE_KEY,
      _fetch: mockFetch([]),
    });
    expect(client.headers.apikey).toBe(FAKE_KEY);
    expect(client.headers["User-Agent"]).toContain("smooth-ts-sdk");
  });
});

describe("SmoothClient API methods", () => {
  it("submits a task", async () => {
    const fetch = mockFetch([
      { body: { r: { id: "t-1", status: "running" } } },
    ]);
    const client = new SmoothClient({ apiKey: FAKE_KEY, _fetch: fetch });

    const handle = await client.run({ task: "Find flights" });
    expect(handle.id()).toBe("t-1");
  });

  it("creates a profile", async () => {
    const fetch = mockFetch([{ body: { r: { id: "p-1" } } }]);
    const client = new SmoothClient({ apiKey: FAKE_KEY, _fetch: fetch });

    const resp = await client.createProfile("my-profile");
    expect(resp.id).toBe("p-1");

    const calls = getCalls(fetch);
    expect(calls[0].url).toContain("/profile");
  });

  it("lists profiles", async () => {
    const fetch = mockFetch([
      { body: { r: [{ id: "p-1" }, { id: "p-2" }] } },
    ]);
    const client = new SmoothClient({ apiKey: FAKE_KEY, _fetch: fetch });

    const profiles = await client.listProfiles();
    expect(profiles).toHaveLength(2);
    expect(profiles[0].id).toBe("p-1");
  });

  it("deletes a profile", async () => {
    const fetch = mockFetch([{ body: { r: {} } }]);
    const client = new SmoothClient({ apiKey: FAKE_KEY, _fetch: fetch });

    await expect(client.deleteProfile("p-1")).resolves.toBeUndefined();
    const calls = getCalls(fetch);
    expect(calls[0].url).toContain("/profile/p-1");
  });

  it("uploads a file", async () => {
    const fetch = mockFetch([{ body: { r: { id: "f-1" } } }]);
    const client = new SmoothClient({ apiKey: FAKE_KEY, _fetch: fetch });

    const resp = await client.uploadFile(Buffer.from("test"), {
      name: "test.pdf",
    });
    expect(resp.id).toBe("f-1");
  });

  it("upload file requires name", async () => {
    const client = new SmoothClient({
      apiKey: FAKE_KEY,
      _fetch: mockFetch([]),
    });
    await expect(
      client.uploadFile(Buffer.from("test")),
    ).rejects.toThrow("File name must be provided");
  });

  it("deletes a file", async () => {
    const fetch = mockFetch([{ body: { r: {} } }]);
    const client = new SmoothClient({ apiKey: FAKE_KEY, _fetch: fetch });

    await expect(client.deleteFile("f-1")).resolves.toBeUndefined();
    const calls = getCalls(fetch);
    expect(calls[0].url).toContain("/file/f-1");
  });

  it("uploads an extension", async () => {
    const fetch = mockFetch([{ body: { r: { id: "ext-1" } } }]);
    const client = new SmoothClient({ apiKey: FAKE_KEY, _fetch: fetch });

    const resp = await client.uploadExtension(Buffer.from("ext"), "my-ext.zip");
    expect(resp.id).toBe("ext-1");
  });

  it("lists extensions", async () => {
    const fetch = mockFetch([
      {
        body: {
          r: [{ id: "ext-1", file_name: "ext.zip", creation_time: 123 }],
        },
      },
    ]);
    const client = new SmoothClient({ apiKey: FAKE_KEY, _fetch: fetch });

    const exts = await client.listExtensions();
    expect(exts).toHaveLength(1);
    expect(exts[0].id).toBe("ext-1");
  });

  it("deletes an extension", async () => {
    const fetch = mockFetch([{ body: { r: {} } }]);
    const client = new SmoothClient({ apiKey: FAKE_KEY, _fetch: fetch });

    await expect(client.deleteExtension("ext-1")).resolves.toBeUndefined();
  });
});

describe("SmoothClient error handling", () => {
  it("propagates API error", async () => {
    const fetch = mockFetch([
      { status: 404, body: { detail: "Not found" } },
    ]);
    const client = new SmoothClient({
      apiKey: FAKE_KEY,
      _fetch: fetch,
      retries: 0,
    });

    try {
      await client.createProfile();
      expect.fail("Should have thrown");
    } catch (e) {
      expect(e).toBeInstanceOf(ApiError);
      expect((e as ApiError).statusCode).toBe(404);
    }
  });

  it("wraps network error as ApiError", async () => {
    const fetch = mockFetch([
      { throwError: new TypeError("fetch failed") },
    ]);
    const client = new SmoothClient({
      apiKey: FAKE_KEY,
      _fetch: fetch,
      retries: 0,
    });

    try {
      await client.createProfile();
      expect.fail("Should have thrown");
    } catch (e) {
      expect(e).toBeInstanceOf(ApiError);
      expect((e as ApiError).statusCode).toBe(0);
    }
  });

  it("handles invalid JSON response on success", async () => {
    const fetch = async () =>
      new Response("not json", {
        status: 200,
        headers: { "Content-Type": "text/plain" },
      });
    const client = new SmoothClient({
      apiKey: FAKE_KEY,
      _fetch: fetch as typeof globalThis.fetch,
      retries: 0,
    });

    try {
      await client.createProfile();
      expect.fail("Should have thrown");
    } catch (e) {
      expect(e).toBeInstanceOf(ApiError);
      expect((e as ApiError).detail).toContain("Invalid JSON");
    }
  });

  it("handles error with non-JSON body", async () => {
    const fetch = mockFetch([
      { status: 500, body: { detail: "Internal Server Error" } },
    ]);
    const client = new SmoothClient({
      apiKey: FAKE_KEY,
      _fetch: fetch,
      retries: 0,
    });

    try {
      await client.createProfile();
      expect.fail("Should have thrown");
    } catch (e) {
      expect(e).toBeInstanceOf(ApiError);
      expect((e as ApiError).statusCode).toBe(500);
      expect((e as ApiError).detail).toContain("Internal Server Error");
    }
  });

  it("handles error with empty detail falls back to HTTP code", async () => {
    const fetch = mockFetch([
      { status: 502, body: { error: "some_error", code: "INVALID" } },
    ]);
    const client = new SmoothClient({
      apiKey: FAKE_KEY,
      _fetch: fetch,
      retries: 0,
    });

    try {
      await client.createProfile();
      expect.fail("Should have thrown");
    } catch (e) {
      expect(e).toBeInstanceOf(ApiError);
      expect((e as ApiError).detail).toContain("HTTP 502");
    }
  });

  it("retries on 5xx errors", async () => {
    const fetch = mockFetch([
      { status: 500, body: { detail: "Server error" } },
      { body: { r: { id: "p-1" } } },
    ]);
    const client = new SmoothClient({
      apiKey: FAKE_KEY,
      _fetch: fetch,
      retries: 1,
    });

    const resp = await client.createProfile();
    expect(resp.id).toBe("p-1");
    expect(getCalls(fetch)).toHaveLength(2);
  });

  it("does not retry on 4xx errors", async () => {
    const fetch = mockFetch([
      { status: 422, body: { detail: "Validation failed" } },
    ]);
    const client = new SmoothClient({
      apiKey: FAKE_KEY,
      _fetch: fetch,
      retries: 3,
    });

    await expect(client.createProfile()).rejects.toThrow(ApiError);
    expect(getCalls(fetch)).toHaveLength(1);
  });
});

describe("SmoothClient internal methods", () => {
  it("_getTask fetches with query params", async () => {
    const fetch = mockFetch([
      { body: { r: { id: "t-1", status: "running" } } },
    ]);
    const client = new SmoothClient({ apiKey: FAKE_KEY, _fetch: fetch });

    const resp = await client._getTask("t-1", { event_t: 100 });
    expect(resp.id).toBe("t-1");
    expect(getCalls(fetch)[0].url).toContain("event_t=100");
  });

  it("_getTask rejects empty id", async () => {
    const client = new SmoothClient({
      apiKey: FAKE_KEY,
      _fetch: mockFetch([]),
    });
    await expect(client._getTask("")).rejects.toThrow(
      "Task ID cannot be empty",
    );
  });

  it("_deleteTask works", async () => {
    const fetch = mockFetch([{ body: { r: {} } }]);
    const client = new SmoothClient({ apiKey: FAKE_KEY, _fetch: fetch });

    await expect(client._deleteTask("t-1")).resolves.toBeUndefined();
    expect(getCalls(fetch)[0].url).toContain("/task/t-1");
    expect(getCalls(fetch)[0].init.method).toBe("DELETE");
  });

  it("_deleteTask rejects empty id", async () => {
    const client = new SmoothClient({
      apiKey: FAKE_KEY,
      _fetch: mockFetch([]),
    });
    await expect(client._deleteTask("")).rejects.toThrow(
      "Task ID cannot be empty",
    );
  });

  it("_sendTaskEvent works", async () => {
    const fetch = mockFetch([{ body: { r: { id: "e-1" } } }]);
    const client = new SmoothClient({ apiKey: FAKE_KEY, _fetch: fetch });

    const resp = await client._sendTaskEvent("t-1", {
      name: "tool_call",
      payload: { code: 200, output: "ok" },
    });
    expect(resp.id).toBe("e-1");
    expect(getCalls(fetch)[0].url).toContain("/task/t-1/event");
  });

  it("_sendTaskEvent rejects empty task id", async () => {
    const client = new SmoothClient({
      apiKey: FAKE_KEY,
      _fetch: mockFetch([]),
    });
    await expect(
      client._sendTaskEvent("", { name: "test", payload: {} }),
    ).rejects.toThrow("Task ID cannot be empty");
  });
});

describe("SmoothClient tool registration", () => {
  it("creates a SmoothTool", () => {
    const client = new SmoothClient({
      apiKey: FAKE_KEY,
      _fetch: mockFetch([]),
    });
    const tool = client.tool(
      {
        name: "my_tool",
        description: "test",
        inputs: { x: "number" },
        output: "string",
      },
      async ({ x }) => `result: ${x}`,
    );
    expect(tool.name).toBe("my_tool");
    expect(tool.signature.description).toBe("test");
  });
});
