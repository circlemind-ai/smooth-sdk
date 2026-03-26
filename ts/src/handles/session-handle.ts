import type {
  TaskEvent,
  TaskResponse,
  ActionGotoResponse,
  ActionExtractResponse,
  ActionEvaluateJSResponse,
  ActionRunTaskResponse,
  ActionCloseResponse,
  Secret,
} from "../models/types.js";
import {
  ActionGotoResponseSchema,
  ActionExtractResponseSchema,
  ActionEvaluateJSResponseSchema,
  ActionRunTaskResponseSchema,
  ActionCloseResponseSchema,
} from "../models/schemas.js";
import { BadRequestError } from "../errors.js";
import { Telemetry } from "../telemetry.js";
import { TaskHandle } from "./task-handle.js";
import type { SmoothClient } from "../client.js";
import type { SmoothTool } from "../tools.js";

export class SessionHandle extends TaskHandle {
  private _closed = false;

  constructor(
    taskId: string,
    client: SmoothClient,
    tools?: SmoothTool[] | null,
  ) {
    super(taskId, client, tools);
  }

  async goto(url: string): Promise<ActionGotoResponse> {
    const start = performance.now();
    try {
      const event: TaskEvent = {
        name: "browser_action",
        payload: {
          name: "goto",
          input: { url },
        },
      };
      const output = await this._sendEvent(event, true);
      const result = ActionGotoResponseSchema.parse(output ?? {});
      Telemetry.get().record("session.goto", {
        properties: { url },
        durationMs: performance.now() - start,
      });
      return result;
    } catch (e) {
      Telemetry.get().record("session.goto", {
        properties: { url },
        durationMs: performance.now() - start,
        error: String(e),
        errorType: e instanceof Error ? e.constructor.name : "Unknown",
      });
      throw e;
    }
  }

  async extract(
    schema: Record<string, unknown>,
    prompt?: string | null,
  ): Promise<ActionExtractResponse> {
    const start = performance.now();
    try {
      const event: TaskEvent = {
        name: "browser_action",
        payload: {
          name: "extract",
          input: { schema, prompt: prompt ?? null },
        },
      };
      const output = await this._sendEvent(event, true);
      const result = ActionExtractResponseSchema.parse(output ?? {});
      Telemetry.get().record("session.extract", {
        properties: { prompt: prompt ?? null },
        durationMs: performance.now() - start,
      });
      return result;
    } catch (e) {
      Telemetry.get().record("session.extract", {
        properties: { prompt: prompt ?? null },
        durationMs: performance.now() - start,
        error: String(e),
        errorType: e instanceof Error ? e.constructor.name : "Unknown",
      });
      throw e;
    }
  }

  async evaluateJs(
    code: string,
    args?: Record<string, unknown> | null,
  ): Promise<ActionEvaluateJSResponse> {
    const start = performance.now();
    try {
      const event: TaskEvent = {
        name: "browser_action",
        payload: {
          name: "evaluate_js",
          input: { js: code, args: args ?? null },
        },
      };
      const output = await this._sendEvent(event, true);
      const result = ActionEvaluateJSResponseSchema.parse(output ?? {});
      Telemetry.get().record("session.evaluate_js", {
        properties: { code, has_args: args != null },
        durationMs: performance.now() - start,
      });
      return result;
    } catch (e) {
      Telemetry.get().record("session.evaluate_js", {
        properties: { code, has_args: args != null },
        durationMs: performance.now() - start,
        error: String(e),
        errorType: e instanceof Error ? e.constructor.name : "Unknown",
      });
      throw e;
    }
  }

  async runTask(options: {
    task: string;
    maxSteps?: number;
    responseModel?: Record<string, unknown> | null;
    url?: string | null;
    metadata?: Record<string, unknown> | null;
    secrets?: Record<string, Secret> | null;
  }): Promise<ActionRunTaskResponse> {
    const start = performance.now();
    try {
      const event: TaskEvent = {
        name: "session_action",
        payload: {
          name: "run_task",
          input: {
            task: options.task,
            max_steps: options.maxSteps ?? 32,
            response_model: options.responseModel ?? null,
            url: options.url ?? null,
            metadata: options.metadata ?? null,
            secrets: options.secrets ?? null,
          },
        },
      };
      const output = await this._sendEvent(event, true);
      const result = ActionRunTaskResponseSchema.parse(output ?? {});
      Telemetry.get().record("session.run_task", {
        properties: {
          task: options.task,
          max_steps: options.maxSteps ?? 32,
          has_response_model: options.responseModel != null,
          url: options.url ?? null,
        },
        durationMs: performance.now() - start,
      });
      return result;
    } catch (e) {
      Telemetry.get().record("session.run_task", {
        properties: {
          task: options.task,
          max_steps: options.maxSteps ?? 32,
          has_response_model: options.responseModel != null,
          url: options.url ?? null,
        },
        durationMs: performance.now() - start,
        error: String(e),
        errorType: e instanceof Error ? e.constructor.name : "Unknown",
      });
      throw e;
    }
  }

  async close(force: boolean = true): Promise<boolean> {
    const start = performance.now();
    this._closed = true;

    try {
      let result: ActionCloseResponse;
      if (!force) {
        const event: TaskEvent = {
          name: "session_action",
          payload: { name: "close" },
        };
        try {
          const output = await this._sendEvent(event, true);
          result = ActionCloseResponseSchema.parse(output ?? {});
        } catch (e) {
          if (e instanceof Error && !(e instanceof BadRequestError)) {
            // A runtime error means session was successfully closed and polling stopped
            result = { output: true, credits_used: 0, duration: 0 };
          } else {
            throw e;
          }
        }
      } else {
        await this._client._deleteTask(this._id);
        result = { output: true, credits_used: 0, duration: 0 };
      }

      if (result.output) {
        this._disconnect(force);
        this._stopProxy();
      }

      Telemetry.get().record("session.close", {
        properties: { force },
        durationMs: (performance.now() - start),
      });
      return result.output;
    } catch (e) {
      Telemetry.get().record("session.close", {
        properties: { force },
        durationMs: (performance.now() - start),
        error: String(e),
        errorType: e instanceof Error ? e.constructor.name : "Unknown",
      });
      throw e;
    }
  }

  async result(options?: { timeout?: number }): Promise<TaskResponse> {
    if (
      this._taskResponse &&
      !["running", "waiting"].includes(this._taskResponse.status)
    ) {
      return this._taskResponse;
    }
    if (!this._closed) {
      throw new BadRequestError(
        "result() cannot be called on an open session. " +
          "Close the session first with close(), or use client.run() for one-shot tasks.",
      );
    }
    return super.result(options);
  }

  async [Symbol.asyncDispose](): Promise<void> {
    if (!this._closed) {
      await this.close(true);
    }
  }
}
