import { describe, it, expect, vi, beforeEach } from "vitest";
import { SessionHandle } from "../src/handles/session-handle.js";
import { SmoothClient } from "../src/client.js";
import { BadRequestError } from "../src/errors.js";
import { Telemetry } from "../src/telemetry.js";

const FAKE_KEY = "cmzr-test-key-0123456789abcdef";

beforeEach(() => {
  Telemetry.reset();
});

function createMockClient(): SmoothClient {
  const client = new SmoothClient({
    apiKey: FAKE_KEY,
    _fetch: (async () => new Response("{}")) as typeof fetch,
  });

  client._getTask = vi.fn(async () => ({
    id: "t-1",
    status: "running",
  }) as any);
  client._deleteTask = vi.fn(async () => {});
  client._sendTaskEvent = vi.fn(async () => ({ id: "e-1" }));

  return client;
}

describe("SessionHandle", () => {
  describe("close", () => {
    it("force close deletes task", async () => {
      const client = createMockClient();
      const session = new SessionHandle("t-1", client);

      const result = await session.close(true);
      expect(result).toBe(true);
      expect(client._deleteTask).toHaveBeenCalledWith("t-1");
    });

    it("graceful close sends close event", async () => {
      const client = createMockClient();
      const session = new SessionHandle("t-1", client);

      // Mock _sendEvent to return close response
      session._sendEvent = vi.fn(async (event) => {
        if (event.payload.name === "close") {
          return { output: true, credits_used: 0, duration: 0 };
        }
        return null;
      });

      const result = await session.close(false);
      expect(result).toBe(true);
      expect(session._sendEvent).toHaveBeenCalledWith(
        expect.objectContaining({
          name: "session_action",
          payload: { name: "close" },
        }),
        true,
      );
    });

    it("graceful close handles runtime error as success", async () => {
      const client = createMockClient();
      const session = new SessionHandle("t-1", client);

      session._sendEvent = vi.fn(async () => {
        throw new Error("polling stopped");
      });

      const result = await session.close(false);
      expect(result).toBe(true);
    });
  });

  describe("result", () => {
    it("raises if session not closed", async () => {
      const client = createMockClient();
      const session = new SessionHandle("t-1", client);

      await expect(session.result()).rejects.toThrow(BadRequestError);
      await expect(session.result()).rejects.toThrow(
        "result() cannot be called on an open session",
      );
    });

    it("returns cached terminal response", async () => {
      const client = createMockClient();
      const session = new SessionHandle("t-1", client);
      session._taskResponse = {
        id: "t-1",
        status: "done",
        output: "result",
      } as any;

      const result = await session.result();
      expect(result.output).toBe("result");
    });
  });

  describe("goto", () => {
    it("sends correct event", async () => {
      const client = createMockClient();
      const session = new SessionHandle("t-1", client);

      session._sendEvent = vi.fn(async (event) => {
        expect(event.name).toBe("browser_action");
        expect(event.payload.name).toBe("goto");
        expect(event.payload.input.url).toBe("https://example.com");
        return { credits_used: 0, duration: 0 };
      });

      await session.goto("https://example.com");
      expect(session._sendEvent).toHaveBeenCalledTimes(1);
    });
  });

  describe("extract", () => {
    it("sends correct event", async () => {
      const client = createMockClient();
      const session = new SessionHandle("t-1", client);

      session._sendEvent = vi.fn(async (event) => {
        expect(event.name).toBe("browser_action");
        expect(event.payload.name).toBe("extract");
        expect(event.payload.input.schema).toEqual({ name: "string" });
        expect(event.payload.input.prompt).toBe("Extract name");
        return { output: { name: "test" }, credits_used: 0, duration: 0 };
      });

      const result = await session.extract({ name: "string" }, "Extract name");
      expect(result.output).toEqual({ name: "test" });
    });

    it("sends null prompt when not provided", async () => {
      const client = createMockClient();
      const session = new SessionHandle("t-1", client);

      session._sendEvent = vi.fn(async (event) => {
        expect(event.payload.input.prompt).toBeNull();
        return { output: {}, credits_used: 0, duration: 0 };
      });

      await session.extract({ name: "string" });
    });
  });

  describe("evaluateJs", () => {
    it("sends correct event", async () => {
      const client = createMockClient();
      const session = new SessionHandle("t-1", client);

      session._sendEvent = vi.fn(async (event) => {
        expect(event.name).toBe("browser_action");
        expect(event.payload.name).toBe("evaluate_js");
        expect(event.payload.input.js).toBe("return 1+1");
        expect(event.payload.input.args).toEqual({ x: 1 });
        return { output: 2, credits_used: 0, duration: 0 };
      });

      const result = await session.evaluateJs("return 1+1", { x: 1 });
      expect(result.output).toBe(2);
    });

    it("sends null args when not provided", async () => {
      const client = createMockClient();
      const session = new SessionHandle("t-1", client);

      session._sendEvent = vi.fn(async (event) => {
        expect(event.payload.input.args).toBeNull();
        return { output: 42, credits_used: 0, duration: 0 };
      });

      await session.evaluateJs("return 42");
    });
  });

  describe("runTask", () => {
    it("sends correct event", async () => {
      const client = createMockClient();
      const session = new SessionHandle("t-1", client);

      session._sendEvent = vi.fn(async (event) => {
        expect(event.name).toBe("session_action");
        expect(event.payload.name).toBe("run_task");
        expect(event.payload.input.task).toBe("Do something");
        expect(event.payload.input.max_steps).toBe(16);
        expect(event.payload.input.response_model).toEqual({ type: "object" });
        expect(event.payload.input.url).toBe("https://example.com");
        return { output: "done", credits_used: 0, duration: 0 };
      });

      const result = await session.runTask({
        task: "Do something",
        maxSteps: 16,
        responseModel: { type: "object" },
        url: "https://example.com",
      });
      expect(result.output).toBe("done");
    });

    it("applies defaults for optional params", async () => {
      const client = createMockClient();
      const session = new SessionHandle("t-1", client);

      session._sendEvent = vi.fn(async (event) => {
        expect(event.payload.input.max_steps).toBe(32);
        expect(event.payload.input.response_model).toBeNull();
        expect(event.payload.input.url).toBeNull();
        expect(event.payload.input.metadata).toBeNull();
        return { output: null, credits_used: 0, duration: 0 };
      });

      await session.runTask({ task: "Simple task" });
    });
  });

  describe("asyncDisposable", () => {
    it("closes session on dispose", async () => {
      const client = createMockClient();
      const session = new SessionHandle("t-1", client);

      await session[Symbol.asyncDispose]();
      expect(client._deleteTask).toHaveBeenCalledWith("t-1");
    });

    it("does not close twice", async () => {
      const client = createMockClient();
      const session = new SessionHandle("t-1", client);

      await session.close(true);
      await session[Symbol.asyncDispose]();

      // _deleteTask should only be called once (from close)
      expect(client._deleteTask).toHaveBeenCalledTimes(1);
    });
  });
});
