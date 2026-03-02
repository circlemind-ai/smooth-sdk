import { describe, it, expect } from "vitest";
import {
  TaskRequestSchema,
  TaskResponseSchema,
  ToolSignatureSchema,
  TaskEventSchema,
  CertificateSchema,
  ActionGotoResponseSchema,
  ActionCloseResponseSchema,
  ActionExtractResponseSchema,
  ActionEvaluateJSResponseSchema,
  ActionRunTaskResponseSchema,
  ProfileResponseSchema,
  UploadFileResponseSchema,
  UploadExtensionResponseSchema,
  ExtensionSchema,
} from "../src/models/schemas.js";

describe("TaskRequestSchema", () => {
  it("applies defaults", () => {
    const req = TaskRequestSchema.parse({ task: "do something" });
    expect(req.task).toBe("do something");
    expect(req.agent).toBe("smooth");
    expect(req.max_steps).toBe(32);
    expect(req.device).toBe("desktop");
    expect(req.enable_recording).toBe(true);
    expect(req.stealth_mode).toBe(false);
    expect(req.use_adblock).toBe(true);
    expect(req.use_captcha_solver).toBe(true);
    expect(req.show_cursor).toBe(false);
  });

  it("validates max_steps minimum", () => {
    expect(() => TaskRequestSchema.parse({ task: "x", max_steps: 1 })).toThrow();
  });

  it("validates max_steps maximum", () => {
    expect(() => TaskRequestSchema.parse({ task: "x", max_steps: 200 })).toThrow();
  });

  it("allows null task", () => {
    const req = TaskRequestSchema.parse({ task: null });
    expect(req.task).toBeNull();
  });

  it("allows valid max_steps", () => {
    const req = TaskRequestSchema.parse({ task: "x", max_steps: 64 });
    expect(req.max_steps).toBe(64);
  });

  it("allows all device types", () => {
    for (const device of ["desktop", "mobile", "desktop-lg"] as const) {
      const req = TaskRequestSchema.parse({ task: "x", device });
      expect(req.device).toBe(device);
    }
  });

  it("supports all optional fields", () => {
    const req = TaskRequestSchema.parse({
      task: "test",
      response_model: { type: "object" },
      url: "https://example.com",
      metadata: { key: "value" },
      files: ["f-1"],
      allowed_urls: ["https://*.example.com/*"],
      profile_id: "p-1",
      profile_read_only: true,
      stealth_mode: true,
      proxy_server: "http://proxy.com",
      proxy_username: "user",
      proxy_password: "pass",
      use_adblock: false,
      use_captcha_solver: false,
      extensions: ["ext-1"],
      show_cursor: true,
    });
    expect(req.profile_id).toBe("p-1");
    expect(req.stealth_mode).toBe(true);
    expect(req.show_cursor).toBe(true);
  });
});

describe("TaskResponseSchema", () => {
  it("parses minimal response", () => {
    const resp = TaskResponseSchema.parse({ id: "t-1", status: "running" });
    expect(resp.id).toBe("t-1");
    expect(resp.status).toBe("running");
    expect(resp.output).toBeUndefined();
    expect(resp.live_url).toBeUndefined();
  });

  it("accepts all statuses", () => {
    for (const status of ["waiting", "running", "done", "failed", "cancelled"] as const) {
      const resp = TaskResponseSchema.parse({ id: "t-1", status });
      expect(resp.status).toBe(status);
    }
  });

  it("parses full response", () => {
    const resp = TaskResponseSchema.parse({
      id: "t-1",
      status: "done",
      output: { key: "value" },
      credits_used: 10,
      device: "mobile",
      live_url: "https://live.example.com",
      recording_url: "https://rec.example.com",
      downloads_url: "https://dl.example.com",
      created_at: 1234567890,
      events: [{ name: "tool_call", payload: { name: "test" } }],
    });
    expect(resp.output).toEqual({ key: "value" });
    expect(resp.credits_used).toBe(10);
    expect(resp.device).toBe("mobile");
    expect(resp.events).toHaveLength(1);
  });
});

describe("ToolSignatureSchema", () => {
  it("parses tool signature", () => {
    const sig = ToolSignatureSchema.parse({
      name: "my_tool",
      description: "A test tool",
      inputs: { a: "string" },
      output: "result",
    });
    expect(sig.name).toBe("my_tool");
    expect(sig.inputs).toEqual({ a: "string" });
  });
});

describe("TaskEventSchema", () => {
  it("parses with optional fields", () => {
    const event = TaskEventSchema.parse({ name: "test", payload: {} });
    expect(event.id).toBeUndefined();
    expect(event.timestamp).toBeUndefined();
  });

  it("parses with all fields", () => {
    const event = TaskEventSchema.parse({
      name: "test",
      payload: { data: 1 },
      id: "e-1",
      timestamp: 123,
    });
    expect(event.id).toBe("e-1");
    expect(event.timestamp).toBe(123);
  });
});

describe("CertificateSchema", () => {
  it("accepts string file", () => {
    const cert = CertificateSchema.parse({ file: "base64data" });
    expect(cert.file).toBe("base64data");
  });

  it("accepts buffer file", () => {
    const cert = CertificateSchema.parse({ file: Buffer.from("test") });
    expect(Buffer.isBuffer(cert.file)).toBe(true);
  });

  it("supports optional password and filters", () => {
    const cert = CertificateSchema.parse({
      file: "data",
      password: "secret",
      filters: [["*.example.com"]],
    });
    expect(cert.password).toBe("secret");
    expect(cert.filters).toEqual([["*.example.com"]]);
  });
});

describe("ActionResponseSchemas", () => {
  it("ActionGotoResponse has defaults", () => {
    const r = ActionGotoResponseSchema.parse({});
    expect(r.credits_used).toBe(0);
    expect(r.duration).toBe(0);
  });

  it("ActionCloseResponse includes output", () => {
    const r = ActionCloseResponseSchema.parse({ output: true });
    expect(r.output).toBe(true);
  });

  it("ActionExtractResponse includes output", () => {
    const r = ActionExtractResponseSchema.parse({ output: { name: "test" } });
    expect(r.output).toEqual({ name: "test" });
  });

  it("ActionEvaluateJSResponse includes output", () => {
    const r = ActionEvaluateJSResponseSchema.parse({ output: 42 });
    expect(r.output).toBe(42);
  });

  it("ActionRunTaskResponse includes output", () => {
    const r = ActionRunTaskResponseSchema.parse({ output: "done" });
    expect(r.output).toBe("done");
  });
});

describe("ProfileResponseSchema", () => {
  it("parses profile response", () => {
    const r = ProfileResponseSchema.parse({ id: "p-1" });
    expect(r.id).toBe("p-1");
  });
});

describe("UploadFileResponseSchema", () => {
  it("parses upload response", () => {
    const r = UploadFileResponseSchema.parse({ id: "f-1" });
    expect(r.id).toBe("f-1");
  });
});

describe("UploadExtensionResponseSchema", () => {
  it("parses extension response", () => {
    const r = UploadExtensionResponseSchema.parse({ id: "ext-1" });
    expect(r.id).toBe("ext-1");
  });
});

describe("ExtensionSchema", () => {
  it("parses extension", () => {
    const ext = ExtensionSchema.parse({
      id: "ext-1",
      file_name: "my-ext.zip",
      creation_time: 1234567890,
    });
    expect(ext.id).toBe("ext-1");
    expect(ext.file_name).toBe("my-ext.zip");
    expect(ext.creation_time).toBe(1234567890);
  });
});
