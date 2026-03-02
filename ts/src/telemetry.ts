import os from "node:os";
import { SDK_VERSION } from "./config.js";

const _ENABLED = (process.env.SMOOTH_TELEMETRY ?? "").toLowerCase() !== "off";
const _FLUSH_INTERVAL = 5_000;
const _FLUSH_THRESHOLD = 10;
const _MAX_QUEUE_SIZE = 200;
const _TELEMETRY_URL =
  process.env.SMOOTH_TELEMETRY_URL ??
  "https://api.smooth.sh/api/v1/telemetry";

function _baseProperties(): Record<string, string> {
  return {
    sdk_version: SDK_VERSION,
    node_version: process.version,
    os: os.platform(),
    os_version: os.release(),
    arch: os.arch(),
  };
}

function _makeEvent(
  eventName: string,
  properties?: Record<string, unknown> | null,
  durationMs?: number | null,
  error?: string | null,
  errorType?: string | null,
): Record<string, unknown> {
  const props: Record<string, unknown> = { ..._baseProperties() };
  if (properties) Object.assign(props, properties);
  if (durationMs != null) props.duration_ms = durationMs;
  if (error != null) props.error = error;
  if (errorType != null) props.error_type = errorType;

  return {
    event: eventName,
    timestamp: new Date().toISOString(),
    properties: props,
  };
}

export interface TelemetryBackend {
  sendBatch(
    events: Array<Record<string, unknown>>,
    apiKey: string,
  ): Promise<void>;
  shutdown(): Promise<void>;
}

class HttpBackend implements TelemetryBackend {
  async sendBatch(
    events: Array<Record<string, unknown>>,
    apiKey: string,
  ): Promise<void> {
    try {
      await fetch(_TELEMETRY_URL, {
        method: "POST",
        headers: {
          apikey: apiKey,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ events }),
        signal: AbortSignal.timeout(5_000),
      });
    } catch {
      // Silently ignore telemetry errors
    }
  }

  async shutdown(): Promise<void> {}
}

class NoopBackend implements TelemetryBackend {
  async sendBatch(): Promise<void> {}
  async shutdown(): Promise<void> {}
}

export class Telemetry {
  private static _instance: Telemetry | null = null;

  private _backend: TelemetryBackend;
  private _queue: Array<Record<string, unknown>> = [];
  private _apiKey = "";
  private _timer: ReturnType<typeof setInterval> | null = null;
  private _started = false;

  constructor() {
    this._backend = _ENABLED ? new HttpBackend() : new NoopBackend();

    if (_ENABLED) {
      process.on("beforeExit", () => {
        void this._flushAndShutdown();
      });
    }
  }

  static get(): Telemetry {
    if (!Telemetry._instance) {
      Telemetry._instance = new Telemetry();
    }
    return Telemetry._instance;
  }

  /** Reset singleton (for testing). */
  static reset(): void {
    if (Telemetry._instance) {
      Telemetry._instance._stop();
    }
    Telemetry._instance = null;
  }

  get enabled(): boolean {
    return _ENABLED;
  }

  init(apiKey: string): void {
    if (!_ENABLED) return;
    this._apiKey = apiKey;
    if (!this._started) {
      this._startFlushLoop();
    }
  }

  setBackend(backend: TelemetryBackend): void {
    this._backend = backend;
  }

  record(
    eventName: string,
    options?: {
      properties?: Record<string, unknown> | null;
      durationMs?: number | null;
      error?: string | null;
      errorType?: string | null;
    },
  ): void {
    if (!_ENABLED) return;
    try {
      const event = _makeEvent(
        eventName,
        options?.properties,
        options?.durationMs,
        options?.error,
        options?.errorType,
      );
      if (this._queue.length >= _MAX_QUEUE_SIZE) {
        this._queue.shift();
      }
      this._queue.push(event);

      if (this._queue.length >= _FLUSH_THRESHOLD && this._started) {
        void this._flush();
      }
    } catch {
      // Silently ignore
    }
  }

  private _startFlushLoop(): void {
    if (this._started) return;
    this._timer = setInterval(() => {
      void this._flush();
    }, _FLUSH_INTERVAL);
    this._timer.unref();
    this._started = true;
  }

  private _stop(): void {
    if (this._timer) {
      clearInterval(this._timer);
      this._timer = null;
    }
    this._started = false;
  }

  async _flush(): Promise<void> {
    if (!this._queue.length || !this._apiKey) return;
    const batch: Array<Record<string, unknown>> = [];
    while (this._queue.length > 0 && batch.length < _FLUSH_THRESHOLD) {
      batch.push(this._queue.shift()!);
    }
    if (batch.length > 0) {
      await this._backend.sendBatch(batch, this._apiKey);
    }
  }

  private async _flushAndShutdown(): Promise<void> {
    while (this._queue.length > 0) {
      await this._flush();
    }
    await this._backend.shutdown();
  }
}

export function track<A extends unknown[], R>(
  eventName: string,
  fn: (...args: A) => Promise<R>,
  propertiesFn?: (...args: A) => Record<string, unknown> | null,
): (...args: A) => Promise<R> {
  return async (...args: A): Promise<R> => {
    let props: Record<string, unknown> | null = null;
    try {
      props = propertiesFn?.(...args) ?? null;
    } catch {
      // ignore
    }
    const start = performance.now();
    try {
      const result = await fn(...args);
      const duration = performance.now() - start;
      Telemetry.get().record(eventName, {
        properties: props,
        durationMs: duration,
      });
      return result;
    } catch (e) {
      const duration = performance.now() - start;
      Telemetry.get().record(eventName, {
        properties: props,
        durationMs: duration,
        error: String(e),
        errorType: e instanceof Error ? e.constructor.name : "Unknown",
      });
      throw e;
    }
  };
}
