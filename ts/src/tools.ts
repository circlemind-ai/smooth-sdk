import type { ToolSignature, TaskEvent } from "./models/types.js";
import { ToolCallError } from "./errors.js";

import type { TaskHandle } from "./handles/task-handle.js";

export interface ToolOptions {
  name: string;
  description: string;
  inputs: Record<string, unknown>;
  output: string;
  essential?: boolean;
  errorMessage?: string;
}

export type ToolFunction = (
  input: Record<string, unknown>,
  handle?: TaskHandle,
) => Promise<unknown>;

export class SmoothTool {
  readonly signature: ToolSignature;
  readonly name: string;
  private _fn: ToolFunction;
  private _essential: boolean;
  private _errorMessage: string | undefined;

  constructor(options: ToolOptions & { fn: ToolFunction }) {
    this.signature = {
      name: options.name,
      description: options.description,
      inputs: options.inputs,
      output: options.output,
    };
    this.name = options.name;
    this._fn = options.fn;
    this._essential = options.essential ?? true;
    this._errorMessage = options.errorMessage;
  }

  async call(
    handle: TaskHandle,
    eventId: string,
    kwargs: Record<string, unknown>,
  ): Promise<void> {
    try {
      const response = await this._fn(kwargs, handle);
      await this._handleToolResponse(handle, eventId, response);
    } catch (e) {
      await this._handleToolResponse(handle, eventId, e);
    }
  }

  private async _handleToolResponse(
    handle: TaskHandle,
    eventId: string,
    response: unknown,
  ): Promise<void> {
    if (response instanceof ToolCallError) {
      await handle._sendEvent({
        id: eventId,
        name: "tool_call",
        payload: {
          code: 400,
          output: String(response.message),
        },
      });
    } else if (response instanceof Error) {
      const code = this._essential ? 500 : 400;
      await handle._sendEvent({
        id: eventId,
        name: "tool_call",
        payload: {
          code,
          output: this._errorMessage ?? String(response.message),
        },
      });
      if (this._essential) {
        throw response;
      }
    } else {
      await handle._sendEvent({
        id: eventId,
        name: "tool_call",
        payload: {
          code: 200,
          output: response,
        },
      });
    }
  }
}
