import { describe, it, expect, vi, beforeEach } from "vitest";
import { SmoothTool } from "../src/tools.js";
import { ToolCallError } from "../src/errors.js";
import { TaskHandle } from "../src/handles/task-handle.js";
import { Telemetry } from "../src/telemetry.js";

beforeEach(() => {
  Telemetry.reset();
});

function createMockHandle(): TaskHandle & { sentEvents: Array<{ id: string; name: string; payload: Record<string, unknown> }> } {
  const sentEvents: Array<{ id: string; name: string; payload: Record<string, unknown> }> = [];
  const handle = {
    _id: "t-1",
    _client: {} as never,
    _tools: new Map(),
    _taskResponse: null,
    _pollInterval: 1000,
    id: () => "t-1",
    sentEvents,
    _sendEvent: vi.fn(async (event: { id?: string | null; name: string; payload: Record<string, unknown> }) => {
      sentEvents.push(event as { id: string; name: string; payload: Record<string, unknown> });
      return null;
    }),
    _connect: vi.fn(),
    _disconnect: vi.fn(),
    _startProxy: vi.fn(),
    _stopProxy: vi.fn(),
    _hasProxy: false,
    result: vi.fn(),
    liveUrl: vi.fn(),
    recordingUrl: vi.fn(),
    downloadsUrl: vi.fn(),
  } as unknown as TaskHandle & { sentEvents: typeof sentEvents };
  return handle;
}

describe("SmoothTool", () => {
  it("has name property", () => {
    const tool = new SmoothTool({
      name: "my_tool",
      description: "test",
      inputs: { x: "number" },
      output: "string",
      fn: async () => "result",
    });
    expect(tool.name).toBe("my_tool");
  });

  it("has signature property", () => {
    const tool = new SmoothTool({
      name: "my_tool",
      description: "A test tool",
      inputs: { x: "number" },
      output: "string",
      fn: async () => "result",
    });
    expect(tool.signature.name).toBe("my_tool");
    expect(tool.signature.description).toBe("A test tool");
    expect(tool.signature.inputs).toEqual({ x: "number" });
    expect(tool.signature.output).toBe("string");
  });

  it("calls function with input kwargs", async () => {
    const fn = vi.fn(async (input: Record<string, unknown>) => `x=${input.x}`);
    const tool = new SmoothTool({
      name: "test",
      description: "test",
      inputs: {},
      output: "string",
      fn,
    });

    const handle = createMockHandle();
    await tool.call(handle, "e-1", { x: 42 });

    expect(fn).toHaveBeenCalledWith({ x: 42 }, handle);
    expect(handle.sentEvents).toHaveLength(1);
    expect(handle.sentEvents[0].payload.code).toBe(200);
    expect(handle.sentEvents[0].payload.output).toBe("x=42");
  });

  it("passes handle as second argument", async () => {
    let receivedHandle: unknown = null;
    const tool = new SmoothTool({
      name: "test",
      description: "test",
      inputs: {},
      output: "string",
      fn: async (_input, handle) => {
        receivedHandle = handle;
        return "ok";
      },
    });

    const handle = createMockHandle();
    await tool.call(handle, "e-1", {});

    expect(receivedHandle).toBe(handle);
  });

  it("handles success response with code 200", async () => {
    const tool = new SmoothTool({
      name: "test",
      description: "test",
      inputs: {},
      output: "string",
      fn: async () => "success result",
    });

    const handle = createMockHandle();
    await tool.call(handle, "e-1", {});

    expect(handle.sentEvents[0].payload.code).toBe(200);
    expect(handle.sentEvents[0].payload.output).toBe("success result");
  });

  it("handles ToolCallError with code 400", async () => {
    const tool = new SmoothTool({
      name: "test",
      description: "test",
      inputs: {},
      output: "string",
      fn: async () => {
        throw new ToolCallError("expected error");
      },
    });

    const handle = createMockHandle();
    await tool.call(handle, "e-1", {});

    expect(handle.sentEvents[0].payload.code).toBe(400);
  });

  it("handles essential error with code 500 and raises", async () => {
    const tool = new SmoothTool({
      name: "test",
      description: "test",
      inputs: {},
      output: "string",
      essential: true,
      fn: async () => {
        throw new Error("critical error");
      },
    });

    const handle = createMockHandle();
    await expect(tool.call(handle, "e-1", {})).rejects.toThrow(
      "critical error",
    );

    expect(handle.sentEvents[0].payload.code).toBe(500);
  });

  it("handles non-essential error with code 400 and does not raise", async () => {
    const tool = new SmoothTool({
      name: "test",
      description: "test",
      inputs: {},
      output: "string",
      essential: false,
      fn: async () => {
        throw new Error("minor error");
      },
    });

    const handle = createMockHandle();
    await tool.call(handle, "e-1", {});

    expect(handle.sentEvents[0].payload.code).toBe(400);
  });

  it("uses custom error message", async () => {
    const tool = new SmoothTool({
      name: "test",
      description: "test",
      inputs: {},
      output: "string",
      essential: false,
      errorMessage: "Custom error occurred",
      fn: async () => {
        throw new Error("original");
      },
    });

    const handle = createMockHandle();
    await tool.call(handle, "e-1", {});

    expect(handle.sentEvents[0].payload.output).toBe("Custom error occurred");
  });

  it("defaults to essential=true", async () => {
    const tool = new SmoothTool({
      name: "test",
      description: "test",
      inputs: {},
      output: "string",
      fn: async () => {
        throw new Error("fail");
      },
    });

    const handle = createMockHandle();
    await expect(tool.call(handle, "e-1", {})).rejects.toThrow("fail");
    expect(handle.sentEvents[0].payload.code).toBe(500);
  });
});
