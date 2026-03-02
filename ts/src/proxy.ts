import { execSync, spawn, type ChildProcess } from "node:child_process";
import {
  createWriteStream,
  existsSync,
  mkdirSync,
  unlinkSync,
  chmodSync,
  writeFileSync,
  rmSync,
} from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { pipeline } from "node:stream/promises";
import { createGunzip } from "node:zlib";
import { Readable } from "node:stream";
import { platform, arch } from "node:process";

const FRP_VERSION = "0.66.0";
const FRP_DIR = join(homedir(), ".smooth", "frp");

export interface ProxyConfig {
  serverUrl: string;
  token: string;
  remotePort?: number;
  sessionId?: string;
}

export class FRPProxy {
  readonly config: ProxyConfig;
  private _process: ChildProcess | null = null;
  private _configFile: string | null = null;
  private _binPath: string | null = null;

  constructor(config: ProxyConfig) {
    this.config = {
      remotePort: 1080,
      sessionId: "default",
      ...config,
    };
  }

  static getPlatformInfo(): { osName: string; arch: string; ext: string } {
    let osName: string;
    if (platform === "darwin") osName = "darwin";
    else if (platform === "win32") osName = "windows";
    else osName = "linux";

    let archName: string;
    if (arch === "x64") archName = "amd64";
    else if (arch === "arm64") archName = "arm64";
    else throw new Error(`Unsupported architecture: ${arch}`);

    const ext = platform === "win32" ? "zip" : "tar.gz";
    return { osName, arch: archName, ext };
  }

  async installFrp(): Promise<string> {
    mkdirSync(FRP_DIR, { recursive: true });

    const { osName, arch: archName, ext } = FRPProxy.getPlatformInfo();
    const binName = osName === "windows" ? "frpc.exe" : "frpc";
    const binPath = join(FRP_DIR, binName);

    if (existsSync(binPath)) return binPath;

    const folderName = `frp_${FRP_VERSION}_${osName}_${archName}`;
    const filename = `${folderName}.${ext}`;
    const url = `https://github.com/fatedier/frp/releases/download/v${FRP_VERSION}/${filename}`;

    const tmpPath = join(FRP_DIR, `tmp_${filename}`);
    const extractDir = join(FRP_DIR, "extract_tmp");

    const maxRetries = 3;
    for (let attempt = 0; attempt < maxRetries; attempt++) {
      try {
        const resp = await fetch(url);
        if (!resp.ok || !resp.body) {
          throw new Error(`HTTP ${resp.status}: ${resp.statusText}`);
        }
        const writeStream = createWriteStream(tmpPath);
        await pipeline(Readable.fromWeb(resp.body as never), writeStream);
        break;
      } catch (e) {
        if (attempt === maxRetries - 1) throw e;
        await new Promise((r) => setTimeout(r, 2 ** attempt * 1000));
      }
    }

    mkdirSync(extractDir, { recursive: true });

    if (ext === "zip") {
      // Use system unzip for simplicity
      execSync(`unzip -o "${tmpPath}" -d "${extractDir}"`, { stdio: "ignore" });
    } else {
      // Use tar for .tar.gz
      execSync(`tar -xzf "${tmpPath}" -C "${extractDir}"`, { stdio: "ignore" });
    }

    const src = join(extractDir, folderName, binName);
    const { renameSync } = await import("node:fs");
    if (existsSync(binPath)) unlinkSync(binPath);
    renameSync(src, binPath);

    // Cleanup
    try {
      unlinkSync(tmpPath);
    } catch {
      /* ignore */
    }
    try {
      rmSync(extractDir, { recursive: true, force: true });
    } catch {
      /* ignore */
    }

    if (osName !== "windows") {
      chmodSync(binPath, 0o755);
    }

    return binPath;
  }

  createConfig(): string {
    mkdirSync(FRP_DIR, { recursive: true });

    const configPath = join(FRP_DIR, `frpc_${this.config.sessionId}.yml`);
    const yaml = `
serverAddr: ${this.config.serverUrl}
serverPort: 443
loginFailExit: false
auth:
  method: token
  token: "${this.config.token}"

log:
  level: "error"

transport:
  protocol: "wss"

proxies:
  - name: "socks5_tunnel_${this.config.sessionId}"
    type: "tcp"
    remotePort: ${this.config.remotePort}
    plugin:
      type: "socks5"
`;
    writeFileSync(configPath, yaml);
    return configPath;
  }

  async start(): Promise<void> {
    if (this._process !== null) {
      throw new Error("Proxy is already running");
    }

    try {
      this._binPath = await this.installFrp();
      this._configFile = this.createConfig();

      this._process = spawn(this._binPath, ["-c", this._configFile], {
        stdio: "ignore",
      });

      // Wait briefly to see if process exits immediately
      await new Promise<void>((resolve, reject) => {
        const timer = setTimeout(() => {
          this._process?.removeAllListeners("exit");
          resolve();
        }, 1000);
        timer.unref();

        this._process!.once("exit", (code) => {
          clearTimeout(timer);
          this._cleanup();
          reject(new Error(`FRP process exited immediately with code ${code}`));
        });
      });
    } catch (e) {
      this._cleanup();
      if (e instanceof Error && e.message.startsWith("FRP process exited")) {
        throw e;
      }
      throw new Error(`Failed to start proxy: ${e}`);
    }
  }

  stop(): void {
    this._cleanup();
  }

  private _cleanup(): void {
    if (this._process) {
      try {
        this._process.kill("SIGTERM");
        // Give it a moment, then force kill
        setTimeout(() => {
          try {
            this._process?.kill("SIGKILL");
          } catch {
            /* ignore */
          }
        }, 5000).unref();
      } catch {
        /* ignore */
      }
      this._process = null;
    }

    if (this._configFile) {
      try {
        if (existsSync(this._configFile)) {
          unlinkSync(this._configFile);
        }
      } catch {
        /* ignore */
      }
      this._configFile = null;
    }
  }

  get isRunning(): boolean {
    if (!this._process) return false;
    return this._process.exitCode === null;
  }
}
