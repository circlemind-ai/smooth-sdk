import { randomBytes } from "node:crypto";
import { basename } from "node:path";
import { Readable } from "node:stream";

import { BASE_URL, SDK_VERSION, USER_AGENT } from "./config.js";
import { ApiError } from "./errors.js";
import { Telemetry, track } from "./telemetry.js";
import { logger, processCertificates } from "./utils.js";
import { TaskHandle } from "./handles/task-handle.js";
import { SessionHandle } from "./handles/session-handle.js";
import { SmoothTool, type ToolFunction, type ToolOptions } from "./tools.js";

import type {
  Certificate,
  DeviceType,
  Extension,
  ProfileResponse,
  TaskEvent,
  TaskEventResponse,
  TaskResponse,
  UploadExtensionResponse,
  UploadFileResponse,
} from "./models/types.js";

export interface ProxyConfig {
  proxyServer: string;
  proxyUsername: string;
  proxyPassword: string;
}

export interface ClientOptions {
  apiKey?: string;
  baseUrl?: string;
  apiVersion?: string;
  timeout?: number;
  retries?: number;
  /** @internal Override fetch for testing. */
  _fetch?: typeof globalThis.fetch;
}

export interface RunOptions {
  task: string | null;
  responseModel?: Record<string, unknown> | null;
  url?: string | null;
  metadata?: Record<string, string | number | boolean> | null;
  files?: string[] | null;
  agent?: "smooth" | "smooth-lite";
  maxSteps?: number;
  device?: DeviceType;
  allowedUrls?: string[] | null;
  enableRecording?: boolean;
  profileId?: string | null;
  profileReadOnly?: boolean;
  stealthMode?: boolean;
  proxyServer?: string | null;
  proxyUsername?: string | null;
  proxyPassword?: string | null;
  certificates?: Array<Certificate | Record<string, unknown>> | null;
  useAdblock?: boolean | null;
  useCaptchaSolver?: boolean | null;
  additionalTools?: Record<string, Record<string, unknown> | null> | null;
  customTools?: SmoothTool[] | null;
  experimentalFeatures?: Record<string, unknown> | null;
  extensions?: string[] | null;
  showCursor?: boolean;
}

export type SessionOptions = Omit<RunOptions, "task" | "responseModel" | "url">;

function getProxyUrl(liveUrl: string): string {
  const parsed = new URL(liveUrl);
  const b = parsed.searchParams.get("b");
  if (!b) throw new Error("No proxy URL provided.");

  // Add padding for base64 (Node Buffer handles this automatically)
  const decoded = Buffer.from(b, "base64url").toString("utf-8");
  const proxyUrl = decoded.split("https://").pop() ?? "";
  return proxyUrl
    .replace("browser-live", "browser-proxy")
    .split("?")[0]
    .replace(/\/+$/, "");
}

export class SmoothClient {
  readonly apiKey: string;
  readonly baseUrl: string;
  readonly headers: Record<string, string>;
  private _timeout: number;
  private _retries: number;
  private _fetch: typeof globalThis.fetch;

  constructor(options?: ClientOptions) {
    const apiKey = options?.apiKey ?? process.env.CIRCLEMIND_API_KEY;
    if (!apiKey) {
      throw new Error(
        "API key is required. Provide it directly or set CIRCLEMIND_API_KEY environment variable.",
      );
    }

    const baseUrl = options?.baseUrl ?? BASE_URL;
    if (!baseUrl) throw new Error("Base URL cannot be empty.");

    const apiVersion = options?.apiVersion ?? "v1";

    this.apiKey = apiKey;
    this.baseUrl = `${baseUrl.replace(/\/+$/, "")}/${apiVersion}`;
    this.headers = {
      apikey: this.apiKey,
      "User-Agent": USER_AGENT,
    };
    this._timeout = (options?.timeout ?? 30) * 1000;
    this._retries = options?.retries ?? 3;
    this._fetch = options?._fetch ?? globalThis.fetch;

    Telemetry.get().init(this.apiKey);
  }

  // --- Task / Session ---

  async run(options: RunOptions): Promise<TaskHandle> {
    const start = performance.now();
    try {
      const certificates = processCertificates(options.certificates);
      const customTools = options.customTools ?? null;

      const payload = buildTaskPayload(options, certificates, customTools);
      const initialResponse = await this._submitTask(payload);

      Telemetry.get().record("sdk.run", {
        properties: {
          task: options.task,
          url: options.url,
          device: options.device ?? "desktop",
          max_steps: options.maxSteps ?? 32,
          profile_id: options.profileId,
          stealth_mode: options.stealthMode ?? false,
          use_adblock: options.useAdblock ?? true,
          has_response_model: options.responseModel != null,
          has_custom_tools: customTools != null,
        },
        durationMs: performance.now() - start,
      });

      return new TaskHandle(initialResponse.id, this, customTools);
    } catch (e) {
      Telemetry.get().record("sdk.run", {
        durationMs: performance.now() - start,
        error: String(e),
        errorType: e instanceof Error ? e.constructor.name : "Unknown",
      });
      throw e;
    }
  }

  async session(options?: SessionOptions): Promise<SessionHandle> {
    const opts = options ?? {};
    const start = performance.now();

    const selfProxy = opts.proxyServer === "self";
    let proxyPassword = opts.proxyPassword ?? null;
    if (selfProxy && !proxyPassword) {
      proxyPassword = randomBytes(12).toString("base64url");
    }

    try {
      const runOpts: RunOptions = {
        ...opts,
        task: null,
        proxyPassword,
      };

      const certificates = processCertificates(runOpts.certificates);
      const customTools = runOpts.customTools ?? null;
      const payload = buildTaskPayload(runOpts, certificates, customTools);
      const initialResponse = await this._submitTask(payload);

      const handle = new SessionHandle(
        initialResponse.id,
        this,
        customTools,
      );

      if (selfProxy) {
        try {
          const url = await handle.liveUrl({ timeout: 30 });
          const proxyUrl = getProxyUrl(url);
          handle._startProxy(proxyUrl, proxyPassword!);
        } catch (e) {
          throw new Error("Failed to start self-proxy.");
        }
      }

      Telemetry.get().record("sdk.session", {
        properties: {
          url: null,
          device: opts.device ?? "desktop",
          profile_id: opts.profileId,
          stealth_mode: opts.stealthMode ?? false,
          proxy_server: opts.proxyServer,
        },
        durationMs: performance.now() - start,
      });

      return handle;
    } catch (e) {
      Telemetry.get().record("sdk.session", {
        durationMs: performance.now() - start,
        error: String(e),
        errorType: e instanceof Error ? e.constructor.name : "Unknown",
      });
      throw e;
    }
  }

  tool(
    options: ToolOptions,
    fn: ToolFunction,
  ): SmoothTool {
    return new SmoothTool({ ...options, fn });
  }

  // --- Profile Methods ---

  async createProfile(profileId?: string | null): Promise<ProfileResponse> {
    const data = await this._request("POST", "/profile", {
      body: { id: profileId ?? null },
    });
    return data.r as ProfileResponse;
  }

  async listProfiles(): Promise<ProfileResponse[]> {
    const data = await this._request("GET", "/profile");
    return (data.r as Array<Record<string, unknown>>).map(
      (d) => d as unknown as ProfileResponse,
    );
  }

  async deleteProfile(profileId: string): Promise<void> {
    await this._request("DELETE", `/profile/${profileId}`);
  }

  // --- File Methods ---

  async uploadFile(
    file: Buffer | Blob | ReadableStream,
    options?: { name?: string; purpose?: string },
  ): Promise<UploadFileResponse> {
    const name = options?.name;
    if (!name) {
      throw new Error(
        "File name must be provided.",
      );
    }

    const formData = new FormData();
    const blob =
      file instanceof Blob ? file : new Blob([new Uint8Array(file as Buffer)]);
    formData.append("file", blob, basename(name));
    if (options?.purpose) {
      formData.append("file_purpose", options.purpose);
    }

    const data = await this._request("POST", "/file", { formData });
    return data.r as UploadFileResponse;
  }

  async deleteFile(fileId: string): Promise<void> {
    await this._request("DELETE", `/file/${fileId}`);
  }

  // --- Extension Methods ---

  async uploadExtension(
    file: Buffer | Blob,
    name?: string,
  ): Promise<UploadExtensionResponse> {
    if (!name) {
      throw new Error("Extension name must be provided.");
    }

    const formData = new FormData();
    const blob = file instanceof Blob ? file : new Blob([new Uint8Array(file)]);
    formData.append("file", blob, basename(name));

    const data = await this._request("POST", "/extension", { formData });
    return data.r as UploadExtensionResponse;
  }

  async listExtensions(): Promise<Extension[]> {
    const data = await this._request("GET", "/extension");
    return data.r as Extension[];
  }

  async deleteExtension(extensionId: string): Promise<void> {
    await this._request("DELETE", `/extension/${extensionId}`);
  }

  // --- Internal API Methods ---

  async _submitTask(
    payload: Record<string, unknown>,
  ): Promise<TaskResponse> {
    const data = await this._request("POST", "/task", { body: payload });
    return data.r as TaskResponse;
  }

  async _getTask(
    taskId: string,
    queryParams?: Record<string, unknown>,
  ): Promise<TaskResponse> {
    if (!taskId) throw new Error("Task ID cannot be empty.");

    let path = `/task/${taskId}`;
    if (queryParams) {
      const params = new URLSearchParams();
      for (const [key, value] of Object.entries(queryParams)) {
        if (value !== undefined && value !== null) {
          params.set(key, String(value));
        }
      }
      const qs = params.toString();
      if (qs) path += `?${qs}`;
    }

    const data = await this._request("GET", path);
    return data.r as TaskResponse;
  }

  async _deleteTask(taskId: string): Promise<void> {
    if (!taskId) throw new Error("Task ID cannot be empty.");
    await this._request("DELETE", `/task/${taskId}`);
  }

  async _sendTaskEvent(
    taskId: string,
    event: TaskEvent,
  ): Promise<TaskEventResponse> {
    if (!taskId) throw new Error("Task ID cannot be empty.");
    const data = await this._request("POST", `/task/${taskId}/event`, {
      body: event,
    });
    return data.r as TaskEventResponse;
  }

  // --- Private HTTP Method ---

  private async _request(
    method: string,
    path: string,
    options?: {
      body?: unknown;
      formData?: FormData;
    },
  ): Promise<Record<string, unknown>> {
    const url = `${this.baseUrl}${path}`;
    let lastError: unknown;

    for (let attempt = 0; attempt <= this._retries; attempt++) {
      try {
        const headers: Record<string, string> = { ...this.headers };
        let reqBody: BodyInit | undefined;

        if (options?.formData) {
          reqBody = options.formData;
        } else if (options?.body !== undefined) {
          headers["Content-Type"] = "application/json";
          reqBody = JSON.stringify(options.body);
        }

        const response = await this._fetch(url, {
          method,
          headers,
          body: reqBody,
          signal: AbortSignal.timeout(this._timeout),
        });

        return await this._handleResponse(response);
      } catch (e) {
        lastError = e;
        // Only retry on network errors or 5xx, not 4xx
        if (e instanceof ApiError && e.statusCode > 0 && e.statusCode < 500) {
          throw e;
        }
        if (attempt < this._retries) {
          const backoff = Math.min(0.5 * 2 ** attempt, 10);
          await new Promise((r) => setTimeout(r, backoff * 1000));
        }
      }
    }

    if (lastError instanceof ApiError) throw lastError;
    throw new ApiError(
      0,
      `Request failed: ${lastError}`,
    );
  }

  private async _handleResponse(
    response: Response,
  ): Promise<Record<string, unknown>> {
    if (response.ok) {
      try {
        return (await response.json()) as Record<string, unknown>;
      } catch (e) {
        logger.error(`Failed to parse JSON response: ${e}`);
        throw new ApiError(
          response.status,
          "Invalid JSON response from server",
        );
      }
    }

    let errorData: Record<string, unknown> | null = null;
    let detail: string;
    try {
      errorData = (await response.json()) as Record<string, unknown>;
      detail = (errorData.detail as string) ?? `HTTP ${response.status} error`;
    } catch {
      const text = await response.text();
      detail = text || `HTTP ${response.status} error`;
    }

    logger.error(`API error: ${response.status} - ${detail}`);
    throw new ApiError(response.status, detail, errorData);
  }
}

// --- Helpers ---

function buildTaskPayload(
  options: RunOptions,
  certificates: Certificate[] | null,
  customTools: SmoothTool[] | null,
): Record<string, unknown> {
  return {
    task: options.task,
    response_model: options.responseModel ?? null,
    url: options.url ?? null,
    metadata: options.metadata ?? null,
    files: options.files ?? null,
    agent: options.agent ?? "smooth",
    max_steps: options.maxSteps ?? 32,
    device: options.device ?? "desktop",
    allowed_urls: options.allowedUrls ?? null,
    enable_recording: options.enableRecording ?? true,
    profile_id: options.profileId ?? null,
    profile_read_only: options.profileReadOnly ?? false,
    stealth_mode: options.stealthMode ?? false,
    proxy_server: options.proxyServer ?? null,
    proxy_username: options.proxyUsername ?? null,
    proxy_password: options.proxyPassword ?? null,
    certificates: certificates ?? null,
    use_adblock: options.useAdblock ?? true,
    use_captcha_solver: options.useCaptchaSolver ?? true,
    additional_tools: options.additionalTools ?? null,
    custom_tools: customTools?.map((t) => t.signature) ?? null,
    experimental_features: options.experimentalFeatures ?? null,
    extensions: options.extensions ?? null,
    show_cursor: options.showCursor ?? false,
  };
}
