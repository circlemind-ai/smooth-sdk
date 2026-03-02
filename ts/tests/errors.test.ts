import { describe, it, expect } from "vitest";
import { ApiError, BadRequestError, SmoothTimeoutError, ToolCallError } from "../src/errors.js";

describe("ApiError", () => {
  it("stores attributes", () => {
    const err = new ApiError(404, "Not found", { code: "NOT_FOUND" });
    expect(err.statusCode).toBe(404);
    expect(err.detail).toBe("Not found");
    expect(err.responseData).toEqual({ code: "NOT_FOUND" });
  });

  it("formats message correctly", () => {
    const err = new ApiError(500, "Internal error");
    expect(err.message).toBe("API Error 500: Internal error");
  });

  it("defaults responseData to null", () => {
    const err = new ApiError(400, "Bad");
    expect(err.responseData).toBeNull();
  });

  it("has correct name", () => {
    const err = new ApiError(500, "fail");
    expect(err.name).toBe("ApiError");
    expect(err).toBeInstanceOf(Error);
  });
});

describe("BadRequestError", () => {
  it("creates with message", () => {
    const err = new BadRequestError("invalid");
    expect(err.message).toBe("invalid");
    expect(err.name).toBe("BadRequestError");
    expect(err).toBeInstanceOf(Error);
  });
});

describe("SmoothTimeoutError", () => {
  it("creates with message", () => {
    const err = new SmoothTimeoutError("timed out");
    expect(err.message).toBe("timed out");
    expect(err.name).toBe("TimeoutError");
    expect(err).toBeInstanceOf(Error);
  });
});

describe("ToolCallError", () => {
  it("creates with message", () => {
    const err = new ToolCallError("tool failed");
    expect(err.message).toBe("tool failed");
    expect(err.name).toBe("ToolCallError");
    expect(err).toBeInstanceOf(Error);
  });
});
