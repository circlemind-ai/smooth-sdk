import { describe, it, expect, vi, beforeEach } from "vitest";
import { TaskHandle } from "../src/handles/task-handle.js";
import { SmoothClient } from "../src/client.js";
import { ApiError, BadRequestError, SmoothTimeoutError } from "../src/errors.js";
import { Telemetry } from "../src/telemetry.js";

const FAKE_KEY = "cmzr-test-key-0123456789abcdef";

beforeEach(() => {
  Telemetry.reset();
});

function createMockClient(
  getTaskResponses: Array<Record<string, unknown>>,
): SmoothClient {
  let callIndex = 0;
  const client = new SmoothClient({
    apiKey: FAKE_KEY,
    _fetch: (async () => new Response("{}")) as typeof fetch,
  });

  client._getTask = vi.fn(async () => {
    const resp = getTaskResponses[Math.min(callIndex++, getTaskResponses.length - 1)];
    return resp as any;
  });
  client._deleteTask = vi.fn(async () => {});
  client._sendTaskEvent = vi.fn(async () => ({ id: "e-1" }));

  return client;
}

describe("TaskHandle", () => {
  describe("id", () => {
    it("returns the task id", () => {
      const client = createMockClient([]);
      const handle = new TaskHandle("t-123", client);
      expect(handle.id()).toBe("t-123");
      expect(handle._id).toBe("t-123");
    });
  });

  describe("result", () => {
    it("returns cached terminal response", async () => {
      const client = createMockClient([]);
      const handle = new TaskHandle("t-1", client);
      handle._taskResponse = { id: "t-1", status: "done", output: "hello" } as any;

      const result = await handle.result();
      expect(result.output).toBe("hello");
      expect(client._getTask).not.toHaveBeenCalled();
    });

    it("raises on invalid timeout", async () => {
      const client = createMockClient([]);
      const handle = new TaskHandle("t-1", client);

      await expect(handle.result({ timeout: 0 })).rejects.toThrow(
        "Timeout must be at least 1 second",
      );
    });

    it("polls until done", async () => {
      const client = createMockClient([
        { id: "t-1", status: "running" },
        { id: "t-1", status: "running" },
        { id: "t-1", status: "done", output: "final" },
      ]);
      const handle = new TaskHandle("t-1", client);
      handle._pollInterval = 50;

      const result = await handle.result({ timeout: 5 });
      expect(result.status).toBe("done");
      expect(result.output).toBe("final");
    });

    it("raises timeout when task never completes", async () => {
      const client = createMockClient([
        { id: "t-1", status: "running" },
      ]);
      const handle = new TaskHandle("t-1", client);
      handle._pollInterval = 50;

      await expect(handle.result({ timeout: 1 })).rejects.toThrow(
        SmoothTimeoutError,
      );
    });
  });

  describe("liveUrl", () => {
    it("raises when task is not running", async () => {
      const client = createMockClient([]);
      const handle = new TaskHandle("t-1", client);
      handle._taskResponse = { id: "t-1", status: "done" } as any;

      await expect(handle.liveUrl()).rejects.toThrow(BadRequestError);
    });

    it("returns encoded url when available", async () => {
      const client = createMockClient([
        { id: "t-1", status: "running", live_url: "https://live.example.com" },
      ]);
      const handle = new TaskHandle("t-1", client);
      handle._pollInterval = 50;

      const url = await handle.liveUrl({ timeout: 5 });
      expect(url).toContain("live.example.com");
      expect(url).toContain("interactive=true");
    });

    it("returns cached live url immediately", async () => {
      const client = createMockClient([]);
      const handle = new TaskHandle("t-1", client);
      handle._taskResponse = {
        id: "t-1",
        status: "running",
        live_url: "https://live.example.com",
      } as any;

      const url = await handle.liveUrl();
      expect(url).toContain("live.example.com");
      expect(url).toContain("interactive=true");
    });
  });

  describe("recordingUrl", () => {
    it("returns cached recording url", async () => {
      const client = createMockClient([]);
      const handle = new TaskHandle("t-1", client);
      handle._taskResponse = {
        id: "t-1",
        status: "done",
        recording_url: "https://rec.example.com",
      } as any;

      const url = await handle.recordingUrl();
      expect(url).toBe("https://rec.example.com");
    });

    it("raises when recording url is empty string", async () => {
      const client = createMockClient([]);
      const handle = new TaskHandle("t-1", client);
      handle._taskResponse = {
        id: "t-1",
        status: "done",
        recording_url: "",
      } as any;

      await expect(handle.recordingUrl()).rejects.toThrow(ApiError);
    });
  });

  describe("proxy", () => {
    it("has proxy is false initially", () => {
      const client = createMockClient([]);
      const handle = new TaskHandle("t-1", client);
      expect(handle._hasProxy).toBe(false);
    });

    it("stop proxy when no proxy is noop", () => {
      const client = createMockClient([]);
      const handle = new TaskHandle("t-1", client);
      // Should not throw
      handle._stopProxy();
      expect(handle._hasProxy).toBe(false);
    });
  });

  describe("connection management", () => {
    it("disconnect decrements alive counter", async () => {
      const client = createMockClient([
        { id: "t-1", status: "running" },
      ]);
      const handle = new TaskHandle("t-1", client);
      handle._pollInterval = 50;

      await handle._connect();
      await handle._connect();
      expect(handle["_isAlive"]).toBe(2);

      handle._disconnect();
      expect(handle["_isAlive"]).toBe(1);

      handle._disconnect();
      expect(handle["_isAlive"]).toBe(0);
    });

    it("disconnect force sets status to cancelled", async () => {
      const client = createMockClient([
        { id: "t-1", status: "running" },
      ]);
      const handle = new TaskHandle("t-1", client);
      handle._pollInterval = 50;
      handle._taskResponse = { id: "t-1", status: "running" } as any;

      handle._disconnect(true);
      expect(handle._taskResponse!.status).toBe("cancelled");
    });
  });

  describe("event processing", () => {
    it("resolves event future on browser_action code 200", async () => {
      let resolveGetTask: ((value: any) => void) | null = null;
      const client = createMockClient([
        { id: "t-1", status: "running" },
      ]);

      // Override _getTask to return events after initial call
      let callCount = 0;
      client._getTask = vi.fn(async () => {
        callCount++;
        if (callCount === 1) {
          return { id: "t-1", status: "running" } as any;
        }
        // Return an event that resolves our deferred
        return {
          id: "t-1",
          status: "running",
          events: [
            {
              id: "evt-1",
              name: "browser_action",
              payload: { code: 200, output: { result: "data" } },
              timestamp: 1,
            },
          ],
        } as any;
      });

      const handle = new TaskHandle("t-1", client);
      handle._pollInterval = 50;

      // Simulate _sendEvent which creates a deferred and waits
      const event = { name: "browser_action", payload: { name: "goto", input: { url: "test" } }, id: "evt-1" };

      // Start connection to begin polling
      await handle._connect();

      // Manually set up a deferred
      let resolveDeferred!: (value: unknown) => void;
      let rejectDeferred!: (reason: unknown) => void;
      const promise = new Promise((res, rej) => {
        resolveDeferred = res;
        rejectDeferred = rej;
      });
      handle["_eventDeferreds"].set("evt-1", {
        promise,
        resolve: resolveDeferred,
        reject: rejectDeferred,
      });

      // Wait for polling to resolve it
      const result = await promise;
      expect(result).toEqual({ result: "data" });

      handle._disconnect();
    });
  });
});
