import { describe, it, expect, vi, beforeEach } from "vitest";
import { FRPProxy } from "../src/proxy.js";

describe("FRPProxy", () => {
  describe("constructor", () => {
    it("applies defaults", () => {
      const proxy = new FRPProxy({
        serverUrl: "proxy.example.com",
        token: "test-token",
      });
      expect(proxy.config.remotePort).toBe(1080);
      expect(proxy.config.sessionId).toBe("default");
    });

    it("accepts custom values", () => {
      const proxy = new FRPProxy({
        serverUrl: "proxy.example.com",
        token: "test-token",
        remotePort: 9999,
        sessionId: "s-1",
      });
      expect(proxy.config.remotePort).toBe(9999);
      expect(proxy.config.sessionId).toBe("s-1");
    });
  });

  describe("getPlatformInfo", () => {
    it("returns three properties", () => {
      const info = FRPProxy.getPlatformInfo();
      expect(info).toHaveProperty("osName");
      expect(info).toHaveProperty("arch");
      expect(info).toHaveProperty("ext");
      expect(["linux", "darwin", "windows"]).toContain(info.osName);
      expect(["amd64", "arm64"]).toContain(info.arch);
      expect(["tar.gz", "zip"]).toContain(info.ext);
    });
  });

  describe("createConfig", () => {
    it("creates YAML config file", () => {
      const proxy = new FRPProxy({
        serverUrl: "proxy.example.com",
        token: "test-token",
        sessionId: "my-session",
      });

      const configPath = proxy.createConfig();
      expect(configPath).toContain("my-session");

      // Read and verify content
      const { readFileSync, unlinkSync } = require("node:fs");
      const content = readFileSync(configPath, "utf-8");
      expect(content).toContain("proxy.example.com");
      expect(content).toContain("test-token");
      expect(content).toContain("socks5");
      expect(content).toContain("my-session");

      // Cleanup
      unlinkSync(configPath);
    });
  });

  describe("isRunning", () => {
    it("is false initially", () => {
      const proxy = new FRPProxy({
        serverUrl: "test",
        token: "test",
      });
      expect(proxy.isRunning).toBe(false);
    });
  });

  describe("stop", () => {
    it("is safe to call when not started", () => {
      const proxy = new FRPProxy({
        serverUrl: "test",
        token: "test",
      });
      // Should not throw
      proxy.stop();
      expect(proxy.isRunning).toBe(false);
    });
  });
});
