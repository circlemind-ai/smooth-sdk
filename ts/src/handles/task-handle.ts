import { randomBytes } from "node:crypto";

function nanoid(size = 21): string {
  return randomBytes(size).toString("base64url").slice(0, size);
}
import type { TaskEvent, TaskResponse } from "../models/types.js";
import {
  ApiError,
  BadRequestError,
  SmoothTimeoutError,
  ToolCallError,
} from "../errors.js";
import { encodeUrl, logger } from "../utils.js";
import { FRPProxy, type ProxyConfig as FRPProxyConfig } from "../proxy.js";
import type { SmoothTool } from "../tools.js";
import type { SmoothClient } from "../client.js";

interface Deferred<T> {
  promise: Promise<T>;
  resolve: (value: T) => void;
  reject: (reason: unknown) => void;
}

function createDeferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

export class TaskHandle {
  readonly _id: string;
  _taskResponse: TaskResponse | null = null;
  _client: SmoothClient;
  _tools: Map<string, SmoothTool>;

  private _isAlive = 0;
  _pollInterval = 1000;
  private _pollingTimer: ReturnType<typeof setTimeout> | null = null;
  private _pollingActive = false;
  private _lastEventT = 0;

  private _eventDeferreds: Map<string, Deferred<unknown>> = new Map();
  private _toolTasks: Map<string, Promise<unknown>> = new Map();

  private _proxy: FRPProxy | null = null;

  constructor(
    taskId: string,
    client: SmoothClient,
    tools?: SmoothTool[] | null,
  ) {
    this._id = taskId;
    this._client = client;
    this._tools = new Map(
      (tools ?? []).map((t) => [t.name, t]),
    );
  }

  id(): string {
    return this._id;
  }

  async result(options?: { timeout?: number }): Promise<TaskResponse> {
    const timeout = options?.timeout;

    if (
      this._taskResponse &&
      !["running", "waiting"].includes(this._taskResponse.status)
    ) {
      return this._taskResponse;
    }

    if (timeout !== undefined && timeout < 1) {
      throw new Error("Timeout must be at least 1 second.");
    }

    return this._withConnection(async () => {
      const start = Date.now();
      while (true) {
        if (
          this._taskResponse &&
          !["running", "waiting"].includes(this._taskResponse.status)
        ) {
          return this._taskResponse;
        }

        if (timeout !== undefined && (Date.now() - start) / 1000 >= timeout) {
          throw new SmoothTimeoutError(
            `Task ${this.id()} did not complete within ${timeout} seconds.`,
          );
        }

        await new Promise((r) => setTimeout(r, 200));
      }
    });
  }

  async liveUrl(options?: {
    interactive?: boolean;
    embed?: boolean;
    timeout?: number;
  }): Promise<string> {
    const interactive = options?.interactive ?? true;
    const embed = options?.embed ?? false;
    const timeout = options?.timeout;

    if (
      this._taskResponse &&
      !["waiting", "running"].includes(this._taskResponse.status)
    ) {
      throw new BadRequestError(
        `Live URL not available for task ${this.id()} as it is ${this._taskResponse.status}.`,
      );
    }

    if (this._taskResponse?.live_url) {
      return encodeUrl(this._taskResponse.live_url, interactive, embed);
    }

    return this._withConnection(async () => {
      const start = Date.now();
      while (true) {
        if (this._taskResponse) {
          if (
            !["waiting", "running"].includes(this._taskResponse.status)
          ) {
            throw new BadRequestError(
              `Live URL not available for task ${this.id()} as it is ${this._taskResponse.status}.`,
            );
          }
          if (this._taskResponse.live_url) {
            return encodeUrl(
              this._taskResponse.live_url,
              interactive,
              embed,
            );
          }
        }

        if (
          timeout !== undefined &&
          (Date.now() - start) / 1000 >= timeout
        ) {
          break;
        }

        await new Promise((r) => setTimeout(r, 200));
      }

      throw new SmoothTimeoutError(
        `Live URL not available for task ${this.id()}.`,
      );
    });
  }

  async recordingUrl(options?: { timeout?: number }): Promise<string> {
    const timeout = options?.timeout ?? 30;

    if (this._taskResponse?.recording_url != null) {
      if (!this._taskResponse.recording_url) {
        throw new ApiError(
          404,
          `Recording URL not available for task ${this.id()}. Set enableRecording=true when creating the task to enable it.`,
        );
      }
      return this._taskResponse.recording_url;
    }

    return this._withConnection(async () => {
      const start = Date.now();
      while (true) {
        if (this._taskResponse?.recording_url != null) {
          if (!this._taskResponse.recording_url) {
            throw new ApiError(
              404,
              `Recording URL not available for task ${this.id()}. Set enableRecording=true when creating the task to enable it.`,
            );
          }
          return this._taskResponse.recording_url;
        }

        if (
          timeout !== undefined &&
          (Date.now() - start) / 1000 >= timeout
        ) {
          break;
        }

        await new Promise((r) => setTimeout(r, 200));
      }

      if (
        this._taskResponse &&
        ["waiting", "running"].includes(this._taskResponse.status)
      ) {
        throw new BadRequestError(
          `Recording URL not available for task ${this.id()} while it is still running.`,
        );
      }
      throw new SmoothTimeoutError(
        `Recording URL not available for task ${this.id()}.`,
      );
    });
  }

  async downloadsUrl(options?: { timeout?: number }): Promise<string> {
    const timeout = options?.timeout ?? 30;

    if (this._taskResponse?.downloads_url != null) {
      return this._taskResponse.downloads_url;
    }

    return this._withConnection(async () => {
      const start = Date.now();
      while (true) {
        if (
          this._taskResponse &&
          !["waiting", "running"].includes(this._taskResponse.status)
        ) {
          const taskResponse = await this._client._getTask(this.id(), {
            downloads: "true",
          });
          if (taskResponse.downloads_url != null) {
            if (!taskResponse.downloads_url) {
              throw new ApiError(
                404,
                `Downloads URL not available for task ${this.id()}. Make sure the task downloaded files during its execution.`,
              );
            }
            return taskResponse.downloads_url;
          }
          await new Promise((r) => setTimeout(r, 800));
        }

        if (
          timeout !== undefined &&
          (Date.now() - start) / 1000 >= timeout
        ) {
          break;
        }

        await new Promise((r) => setTimeout(r, 200));
      }

      if (
        this._taskResponse &&
        ["waiting", "running"].includes(this._taskResponse.status)
      ) {
        throw new BadRequestError(
          `Downloads URL not available for task ${this.id()} while it is still running.`,
        );
      }
      throw new SmoothTimeoutError(
        `Downloads URL not available for task ${this.id()}.`,
      );
    });
  }

  // --- Proxy Methods ---

  _startProxy(serverUrl: string, token: string): void {
    if (this._proxy?.isRunning) {
      throw new Error(`Proxy for task ${this._id} is already running`);
    }

    this._proxy = new FRPProxy({
      serverUrl,
      token,
      sessionId: this._id,
    });
    void this._proxy.start();
  }

  _stopProxy(): void {
    if (this._proxy) {
      this._proxy.stop();
      this._proxy = null;
    }
  }

  get _hasProxy(): boolean {
    return this._proxy?.isRunning ?? false;
  }

  // --- Event Methods ---

  async _sendEvent(
    event: TaskEvent,
    hasResult: boolean = false,
  ): Promise<unknown | null> {
    const eventWithId = { ...event, id: event.id ?? nanoid() };

    if (hasResult) {
      const deferred = createDeferred<unknown>();
      this._eventDeferreds.set(eventWithId.id!, deferred);

      await this._client._sendTaskEvent(this._id, eventWithId);
      return this._withConnection(() => deferred.promise);
    } else {
      await this._client._sendTaskEvent(this._id, eventWithId);
      return null;
    }
  }

  // --- Connection Management ---

  async _connect(): Promise<void> {
    this._isAlive += 1;
    if (this._isAlive !== 1) return;

    this._taskResponse = await this._client._getTask(this.id(), {
      event_t: this._lastEventT,
    });

    // Stagger start
    await new Promise((r) =>
      setTimeout(r, Math.random() * this._pollInterval),
    );
    this._startPolling();
  }

  _disconnect(force: boolean = false): void {
    this._isAlive = this._isAlive < 1 ? 0 : this._isAlive - 1;
    if (this._isAlive === 0) {
      this._stopPolling();
    }

    if (force && this._taskResponse) {
      (this._taskResponse as { status: string }).status = "cancelled";
    }
  }

  private async _withConnection<T>(fn: () => Promise<T>): Promise<T> {
    await this._connect();
    try {
      return await fn();
    } finally {
      this._disconnect();
    }
  }

  private _startPolling(): void {
    if (this._pollingActive) return;
    this._pollingActive = true;

    const poll = async () => {
      const pollerId = nanoid(8);
      let consecutiveFailures = 0;
      const maxRetries = 5;

      try {
        while (this._isAlive > 0) {
          await new Promise((r) => {
            this._pollingTimer = setTimeout(r, this._pollInterval);
            if (this._pollingTimer && typeof this._pollingTimer === "object" && "unref" in this._pollingTimer) {
              this._pollingTimer.unref();
            }
          });

          if (this._isAlive <= 0) break;

          try {
            const taskResponse = await this._client._getTask(this.id(), {
              event_t: this._lastEventT,
            });
            consecutiveFailures = 0;
            this._taskResponse = taskResponse;

            if (!["running", "waiting"].includes(taskResponse.status)) {
              break;
            }

            if (taskResponse.events) {
              const lastEvent =
                taskResponse.events[taskResponse.events.length - 1];
              if (lastEvent?.timestamp) {
                this._lastEventT = lastEvent.timestamp;
              }

              for (const event of taskResponse.events) {
                if (!event.id) continue;
                this._processEvent(event as TaskEvent & { id: string });
              }
            }

            // Await completed tool tasks to surface errors
            for (const [id, task] of this._toolTasks) {
              try {
                // Check if promise is settled by racing with an immediate resolve
                const result = await Promise.race([
                  task.then(() => "done" as const),
                  Promise.resolve("pending" as const),
                ]);
                if (result === "done") {
                  this._toolTasks.delete(id);
                }
              } catch {
                this._toolTasks.delete(id);
              }
            }
          } catch (e) {
            if (e instanceof ApiError && e.statusCode !== 0) throw e;
            consecutiveFailures++;
            if (consecutiveFailures > maxRetries) throw e;
            const backoff = Math.min(2 ** (consecutiveFailures - 1), 16);
            logger.warn(
              `Poller ${pollerId} transient error (attempt ${consecutiveFailures}/${maxRetries}), retrying in ${backoff}s: ${e}`,
            );
            await new Promise((r) => setTimeout(r, backoff * 1000));
          }
        }
      } catch (e) {
        this._isAlive = 0;

        for (const deferred of this._eventDeferreds.values()) {
          deferred.reject(e);
        }
        this._eventDeferreds.clear();
        this._toolTasks.clear();

        logger.error(
          `Poller ${pollerId} for task ${this.id()} failed: ${e}`,
        );
      }

      this._pollingActive = false;
      logger.debug(`Poller for task ${this.id()} stopped`);
    };

    void poll();
  }

  private _processEvent(event: TaskEvent & { id: string }): void {
    if (
      event.name === "tool_call" &&
      this._tools.has(event.payload.name as string)
    ) {
      const tool = this._tools.get(event.payload.name as string)!;
      const taskPromise = tool
        .call(
          this,
          event.id,
          (event.payload.input as Record<string, unknown>) ?? {},
        )
        .catch((e: unknown) => {
          logger.error(`Tool ${tool.name} failed: ${e}`);
        })
        .finally(() => {
          this._toolTasks.delete(event.id);
        });
      this._toolTasks.set(event.id, taskPromise);
    } else if (
      event.name === "browser_action" ||
      event.name === "session_action"
    ) {
      const deferred = this._eventDeferreds.get(event.id);
      if (deferred) {
        this._eventDeferreds.delete(event.id);
        const code = event.payload.code as number;
        if (code === 200) {
          deferred.resolve(event.payload.output);
        } else if (code === 400) {
          deferred.reject(
            new ToolCallError(
              (event.payload.output as string) ?? "Unknown error.",
            ),
          );
        } else if (code === 500) {
          deferred.reject(
            new Error(
              (event.payload.output as string) ?? "Unknown error.",
            ),
          );
        }
      }
    }
  }

  private _stopPolling(): void {
    if (this._pollingTimer) {
      clearTimeout(this._pollingTimer);
      this._pollingTimer = null;
    }
  }
}
