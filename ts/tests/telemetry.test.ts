import { describe, it, expect, beforeEach, vi } from "vitest";
import { Telemetry, track, type TelemetryBackend } from "../src/telemetry.js";

class MockBackend implements TelemetryBackend {
  batches: Array<{ events: Array<Record<string, unknown>>; apiKey: string }> = [];

  async sendBatch(
    events: Array<Record<string, unknown>>,
    apiKey: string,
  ): Promise<void> {
    this.batches.push({ events: [...events], apiKey });
  }

  async shutdown(): Promise<void> {}
}

beforeEach(() => {
  Telemetry.reset();
});

describe("Telemetry", () => {
  describe("singleton", () => {
    it("returns same instance", () => {
      const a = Telemetry.get();
      const b = Telemetry.get();
      expect(a).toBe(b);
    });
  });

  describe("record", () => {
    it("enqueues event when enabled", () => {
      const t = Telemetry.get();
      const backend = new MockBackend();
      t.setBackend(backend);

      t.record("test.event", { properties: { x: 1 } });

      // Access internal queue through flush
      expect(t["_queue"]).toHaveLength(1);
      expect(t["_queue"][0].event).toBe("test.event");
      expect((t["_queue"][0].properties as Record<string, unknown>).x).toBe(1);
    });

    it("includes base properties in events", () => {
      const t = Telemetry.get();
      t.record("test.event");

      const event = t["_queue"][0];
      const props = event.properties as Record<string, unknown>;
      expect(props).toHaveProperty("sdk_version");
      expect(props).toHaveProperty("node_version");
      expect(props).toHaveProperty("os");
      expect(props).toHaveProperty("os_version");
      expect(props).toHaveProperty("arch");
    });

    it("includes duration_ms when provided", () => {
      const t = Telemetry.get();
      t.record("test.event", { durationMs: 150.5 });

      const props = t["_queue"][0].properties as Record<string, unknown>;
      expect(props.duration_ms).toBe(150.5);
    });

    it("includes error when provided", () => {
      const t = Telemetry.get();
      t.record("test.event", { error: "boom", errorType: "ValueError" });

      const props = t["_queue"][0].properties as Record<string, unknown>;
      expect(props.error).toBe("boom");
      expect(props.error_type).toBe("ValueError");
    });

    it("does not include duration when not provided", () => {
      const t = Telemetry.get();
      t.record("test.event");

      const props = t["_queue"][0].properties as Record<string, unknown>;
      expect(props).not.toHaveProperty("duration_ms");
    });

    it("does not include error when not provided", () => {
      const t = Telemetry.get();
      t.record("test.event");

      const props = t["_queue"][0].properties as Record<string, unknown>;
      expect(props).not.toHaveProperty("error");
      expect(props).not.toHaveProperty("error_type");
    });

    it("includes timestamp", () => {
      const t = Telemetry.get();
      t.record("test.event");
      expect(t["_queue"][0]).toHaveProperty("timestamp");
    });
  });

  describe("flush", () => {
    it("drains queue", async () => {
      const t = Telemetry.get();
      const backend = new MockBackend();
      t.setBackend(backend);
      t.init("test-key");

      for (let i = 0; i < 5; i++) {
        t.record(`event.${i}`);
      }

      await t._flush();

      expect(t["_queue"]).toHaveLength(0);
      expect(backend.batches).toHaveLength(1);
      expect(backend.batches[0].events).toHaveLength(5);
      expect(backend.batches[0].apiKey).toBe("test-key");
    });

    it("does nothing when empty", async () => {
      const t = Telemetry.get();
      const backend = new MockBackend();
      t.setBackend(backend);
      t.init("test-key");

      await t._flush();

      expect(backend.batches).toHaveLength(0);
    });

    it("does nothing without api key", async () => {
      const t = Telemetry.get();
      const backend = new MockBackend();
      t.setBackend(backend);

      t.record("test.event");
      await t._flush();

      expect(backend.batches).toHaveLength(0);
      expect(t["_queue"]).toHaveLength(1);
    });

    it("batches up to threshold per flush call", async () => {
      const t = Telemetry.get();
      const backend = new MockBackend();
      t.setBackend(backend);
      // Don't call init() to avoid auto-flush on threshold
      t["_apiKey"] = "test-key";

      for (let i = 0; i < 25; i++) {
        t["_queue"].push({ event: `event.${i}`, timestamp: new Date().toISOString(), properties: {} });
      }

      await t._flush();

      // Should flush up to threshold (10) per call
      expect(backend.batches[0].events).toHaveLength(10);
      expect(t["_queue"]).toHaveLength(15);
    });
  });
});

describe("track", () => {
  it("records duration on success", async () => {
    const t = Telemetry.get();
    const backend = new MockBackend();
    t.setBackend(backend);

    const fn = track("test.fn", async () => "result");
    const result = await fn();

    expect(result).toBe("result");
    expect(t["_queue"]).toHaveLength(1);
    const props = t["_queue"][0].properties as Record<string, unknown>;
    expect(props).toHaveProperty("duration_ms");
    expect(typeof props.duration_ms).toBe("number");
  });

  it("records error on failure", async () => {
    const t = Telemetry.get();
    const backend = new MockBackend();
    t.setBackend(backend);

    const fn = track("test.fn", async () => {
      throw new Error("test error");
    });

    await expect(fn()).rejects.toThrow("test error");

    expect(t["_queue"]).toHaveLength(1);
    const props = t["_queue"][0].properties as Record<string, unknown>;
    expect(props.error).toContain("test error");
    expect(props.error_type).toBe("Error");
  });

  it("passes custom properties", async () => {
    const t = Telemetry.get();

    const fn = track(
      "test.fn",
      async (url: string) => url,
      (url: string) => ({ url }),
    );

    await fn("https://example.com");

    const props = t["_queue"][0].properties as Record<string, unknown>;
    expect(props.url).toBe("https://example.com");
  });
});
