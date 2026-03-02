import { describe, it, expect } from "vitest";
import { encodeUrl, processCertificates, toSnakeCase, toCamelCase } from "../src/utils.js";

describe("encodeUrl", () => {
  it("sets interactive=true by default", () => {
    const result = encodeUrl("https://example.com?token=abc");
    expect(result).toContain("interactive=true");
    expect(result).toContain("embed=false");
    expect(result).toContain("token=abc");
  });

  it("sets interactive=false", () => {
    const result = encodeUrl("https://example.com", false);
    expect(result).toContain("interactive=false");
  });

  it("sets embed=true", () => {
    const result = encodeUrl("https://example.com", true, true);
    expect(result).toContain("embed=true");
  });

  it("preserves existing query params", () => {
    const result = encodeUrl("https://example.com?foo=bar&baz=1");
    expect(result).toContain("foo=bar");
    expect(result).toContain("baz=1");
    expect(result).toContain("interactive=true");
  });

  it("handles URL with no query string", () => {
    const result = encodeUrl("https://example.com/path", true, true);
    expect(result).toContain("interactive=true");
    expect(result).toContain("embed=true");
    expect(result).toContain("?");
  });

  it("uses defaults", () => {
    const result = encodeUrl("https://example.com");
    expect(result).toContain("interactive=true");
    expect(result).toContain("embed=false");
  });
});

describe("processCertificates", () => {
  it("returns null for null input", () => {
    expect(processCertificates(null)).toBeNull();
  });

  it("returns null for undefined input", () => {
    expect(processCertificates(undefined)).toBeNull();
  });

  it("converts Buffer to base64", () => {
    const data = Buffer.from("hello cert");
    const result = processCertificates([{ file: data, password: "secret" }]);
    expect(result).not.toBeNull();
    expect(result).toHaveLength(1);
    expect(result![0].file).toBe(data.toString("base64"));
    expect(result![0].password).toBe("secret");
  });

  it("passes through string file", () => {
    const result = processCertificates([{ file: "already-base64-encoded" }]);
    expect(result).not.toBeNull();
    expect(result![0].file).toBe("already-base64-encoded");
  });

  it("handles dict input with string", () => {
    const result = processCertificates([{ file: "some-string" }]);
    expect(result).not.toBeNull();
    expect(result![0].file).toBe("some-string");
  });

  it("handles dict input with Buffer", () => {
    const data = Buffer.from("binary data");
    const result = processCertificates([{ file: data }]);
    expect(result).not.toBeNull();
    expect(result![0].file).toBe(data.toString("base64"));
  });

  it("throws on invalid file type", () => {
    expect(() =>
      processCertificates([{ file: 12345 as unknown as string }]),
    ).toThrow("Certificate file must be a string or Buffer");
  });

  it("processes multiple certificates", () => {
    const buf = Buffer.from("cert1");
    const result = processCertificates([
      { file: buf },
      { file: "already-encoded" },
    ]);
    expect(result).not.toBeNull();
    expect(result).toHaveLength(2);
    expect(result![0].file).toBe(buf.toString("base64"));
    expect(result![1].file).toBe("already-encoded");
  });
});

describe("toSnakeCase", () => {
  it("converts camelCase keys to snake_case", () => {
    const result = toSnakeCase({ maxSteps: 32, profileId: "p-1" });
    expect(result).toEqual({ max_steps: 32, profile_id: "p-1" });
  });

  it("leaves already snake_case keys unchanged", () => {
    const result = toSnakeCase({ max_steps: 32 });
    expect(result).toEqual({ max_steps: 32 });
  });
});

describe("toCamelCase", () => {
  it("converts snake_case keys to camelCase", () => {
    const result = toCamelCase({ max_steps: 32, profile_id: "p-1" });
    expect(result).toEqual({ maxSteps: 32, profileId: "p-1" });
  });

  it("leaves already camelCase keys unchanged", () => {
    const result = toCamelCase({ maxSteps: 32 });
    expect(result).toEqual({ maxSteps: 32 });
  });
});
