import axios, { AxiosInstance, AxiosError, AxiosResponse } from 'axios';
import FormData = require('form-data');
import { Readable } from 'stream';
import { URL } from 'url';
import { nanoid } from 'nanoid';

// --- Constants ---
const BASE_URL = 'https://api.smooth.sh/api/';
const SDK_VERSION = '0.4.0';

// --- Utils ---

/**
 * Encodes a URL with interactive and embed parameters.
 * @param url The URL to encode.
 * @param interactive Whether the session is interactive.
 * @param embed Whether the session is embedded.
 * @returns The encoded URL string.
 */
function _encode_url(url: string, interactive: boolean = true, embed: boolean = false): string {
  const parsedUrl = new URL(url);
  const params = parsedUrl.searchParams;
  params.set('interactive', interactive ? 'true' : 'false');
  params.set('embed', embed ? 'true' : 'false');
  parsedUrl.search = params.toString();
  return parsedUrl.toString();
}

/**
 * Pauses execution for a given number of milliseconds.
 * @param ms The number of milliseconds to sleep.
 */
const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * Marks a method as deprecated and logs a warning when called.
 * @param message The deprecation message to display.
 */
function deprecated(message: string): MethodDecorator {
  return function <T>(
    _target: Object,
    propertyKey: string | symbol,
    descriptor: TypedPropertyDescriptor<T>
  ): TypedPropertyDescriptor<T> | void {
    const originalMethod = descriptor.value;
    if (typeof originalMethod === 'function') {
      (descriptor as any).value = function (this: any, ...args: any[]) {
        console.warn(`Warning: '${String(propertyKey)}' is deprecated. ${message}`);
        return (originalMethod as any).apply(this, args);
      };
    }
    return descriptor;
  };
}

// --- Models ---

export type TaskStatus = 'waiting' | 'running' | 'done' | 'failed' | 'cancelled';
export type DeviceType = 'desktop' | 'mobile';
export type AgentType = 'smooth' | 'smooth-lite';

/**
 * Client certificate for accessing secure websites.
 */
export interface Certificate {
  /**
   * p12 file content as a Buffer or a base64 encoded string.
   */
  file: Buffer | string;
  /**
   * Password to decrypt the certificate file. Optional.
   */
  password?: string;
  /**
   * Reserved for future use.
   */
  filters?: string[];
}

/**
 * Interface for the processed certificate payload.
 * @internal
 */
interface ProcessedCertificate {
  file: string; // Base64 encoded string
  password?: string;
  filters?: string[];
}

/**
 * Tool signature defining a custom tool's interface.
 */
export interface ToolSignature {
  name: string;
  description: string;
  inputs: Record<string, any>;
  output: string;
}

/**
 * Task event model.
 */
export interface TaskEvent {
  name: string;
  payload: Record<string, any>;
  id?: string;
  timestamp?: number;
}

/**
 * Task event response model.
 */
export interface TaskEventResponse {
  id: string;
}

export interface TaskResponse {
  id: string;
  status: TaskStatus;
  output: any | null;
  credits_used: number | null;
  device: DeviceType | null;
  live_url: string | null;
  recording_url: string | null;
  downloads_url: string | null;
  created_at: number | null;
  events?: TaskEvent[] | null;
  [key: string]: any; // Allow extra properties as in the Python model
}

/**
 * Interface for the raw task request payload sent to the API.
 * @internal
 */
interface TaskRequestPayload {
  task: string | null;
  response_model?: Record<string, any> | null;
  url?: string | null;
  metadata?: Record<string, string | number | boolean> | null;
  files?: string[] | null;
  agent?: AgentType;
  max_steps?: number;
  device?: DeviceType;
  allowed_urls?: string[] | null;
  enable_recording?: boolean;
  profile_id?: string | null;
  session_id?: string | null; // For retro-compatibility
  profile_read_only?: boolean;
  stealth_mode?: boolean;
  proxy_server?: string | null;
  proxy_username?: string | null;
  proxy_password?: string | null;
  certificates?: ProcessedCertificate[] | null;
  use_adblock?: boolean | null;
  additional_tools?: Record<string, Record<string, any> | null> | null;
  custom_tools?: ToolSignature[] | null;
  experimental_features?: Record<string, any> | null;
  extensions?: string[] | null;
}

/**
 * Options for the `run` method.
 */
export interface RunTaskOptions {
  task: string;
  response_model?: Record<string, any> | null;
  url?: string | null;
  metadata?: Record<string, string | number | boolean> | null;
  files?: string[] | null;
  agent?: AgentType;
  max_steps?: number;
  device?: DeviceType;
  allowed_urls?: string[] | null;
  enable_recording?: boolean;
  /**
   * (Deprecated, use `profile_id` instead) Browser profile ID to use.
   * @deprecated Use `profile_id` instead.
   */
  session_id?: string | null;
  profile_id?: string | null;
  profile_read_only?: boolean;
  stealth_mode?: boolean;
  proxy_server?: string | null;
  proxy_username?: string | null;
  proxy_password?: string | null;
  /**
   * List of client certificates to use when accessing secure websites.
   */
  certificates?: Certificate[] | null;
  /**
   * Enable adblock for the browser session. Default is True.
   */
  use_adblock?: boolean | null;
  /**
   * Additional tools to enable for the task.
   */
  additional_tools?: Record<string, Record<string, any> | null> | null;
  /**
   * Custom tools to register for the task.
   */
  custom_tools?: (SmoothTool | ToolSignature)[] | null;
  experimental_features?: Record<string, any> | null;
  /**
   * List of extension IDs to install for the task.
   */
  extensions?: string[] | null;
}

/**
 * Options for the `session` method.
 */
export interface SessionOptions {
  url?: string | null;
  files?: string[] | null;
  agent?: AgentType;
  device?: DeviceType;
  allowed_urls?: string[] | null;
  enable_recording?: boolean;
  profile_id?: string | null;
  profile_read_only?: boolean;
  stealth_mode?: boolean;
  proxy_server?: string | null;
  proxy_username?: string | null;
  proxy_password?: string | null;
  certificates?: Certificate[] | null;
  use_adblock?: boolean | null;
  additional_tools?: Record<string, Record<string, any> | null> | null;
  custom_tools?: (SmoothTool | ToolSignature)[] | null;
  experimental_features?: Record<string, any> | null;
  extensions?: string[] | null;
}

/**
 * Interface for the raw browser session request payload.
 * @internal
 * @deprecated Use SessionOptions with session() instead.
 */
interface BrowserSessionRequestPayload {
  profile_id?: string | null;
  session_id?: string | null; // For retro-compatibility
  live_view?: boolean | null;
  device?: DeviceType | null;
  url?: string | null;
  proxy_server?: string | null;
  proxy_username?: string | null;
  proxy_password?: string | null;
}

/**
 * Options for the `open_session` method.
 * @deprecated Use SessionOptions with session() instead.
 */
export interface OpenSessionOptions {
  /**
   * (Deprecated, use `profile_id` instead) The profile ID to use.
   * @deprecated Use `profile_id` instead.
   */
  session_id?: string | null;
  profile_id?: string | null;
  live_view?: boolean;
  /**
   * The device type to use for the browser session.
   */
  device?: DeviceType;
  /**
   * The URL to open in the browser session.
   */
  url?: string | null;
  /**
   * Proxy server url to route browser traffic through. Must include the protocol to use (e.g. http:// or https://).
   */
  proxy_server?: string | null;
  /**
   * Proxy server username.
   */
  proxy_username?: string | null;
  /**
   * Proxy server password.
   */
  proxy_password?: string | null;
}

export interface BrowserSessionResponse {
  profile_id: string;
  live_id: string | null;
  live_url: string | null;
}

export interface BrowserProfilesResponse {
  profile_ids: string[];
  session_ids?: string[]; // For retro-compatibility
}

export interface ProfileResponse {
  id: string;
}

export interface UploadFileResponse {
  id: string;
}

export interface UploadExtensionResponse {
  id: string;
}

export interface Extension {
  id: string;
  file_name: string;
  creation_time: number;
}

export interface ListExtensionsResponse {
  extensions: Extension[];
}

/**
 * Response structure for API endpoints.
 * Assumes the actual data is nested under an 'r' key.
 * @internal
 */
interface ApiResponse<T> {
  r: T;
  [key: string]: any;
}

// --- Action Response Models ---

/**
 * Response model for goto action.
 */
export interface ActionGotoResponse {}

/**
 * Response model for extract action.
 */
export interface ActionExtractResponse {
  data: any;
}

/**
 * Response model for evaluate_js action.
 */
export interface ActionEvaluateJSResponse {
  result: any;
}

/**
 * Response model for run_task action.
 */
export interface ActionRunTaskResponse {
  output: any;
}

// --- Exception Handling ---

export class ApiError extends Error {
  public status_code: number;
  public detail: string;
  public response_data: Record<string, any> | null;

  constructor(status_code: number, detail: string, response_data: Record<string, any> | null = null) {
    super(`API Error ${status_code}: ${detail}`);
    this.name = 'ApiError';
    this.status_code = status_code;
    this.detail = detail;
    this.response_data = response_data;
  }
}

export class TimeoutError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'TimeoutError';
  }
}

export class BadRequestError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'BadRequestError';
  }
}

export class ToolCallError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ToolCallError';
  }
}

/**
 * Custom Error for internal use.
 * @internal
 */
class ValueError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ValueError';
  }
}

// --- Custom Tools ---

/**
 * Options for creating a SmoothTool.
 */
export interface SmoothToolOptions {
  signature: ToolSignature;
  fn: ToolFunction;
  essential?: boolean;
  error_message?: string | null;
}

/**
 * Type for tool function that can optionally receive a task handle.
 */
export type ToolFunction = (
  task: TaskHandle | SessionHandle,
  ...args: any[]
) => any | Promise<any>;

/**
 * A custom tool that can be registered with the Smooth client.
 */
export class SmoothTool {
  public signature: ToolSignature;
  private _fn: ToolFunction;
  private _essential: boolean;
  private _error_message: string | null;

  constructor(options: SmoothToolOptions) {
    this.signature = options.signature;
    this._fn = options.fn;
    this._essential = options.essential ?? true;
    this._error_message = options.error_message ?? null;
  }

  /**
   * Returns the tool name.
   */
  public get name(): string {
    return this.signature.name;
  }

  /**
   * Runs the tool function.
   * @internal
   */
  public async _run_fn(task: TaskHandle | SessionHandle, kwargs: Record<string, any>): Promise<any> {
    // Check if the function signature expects a 'task' parameter
    const fnParams = this._fn.length;
    if (fnParams > 0) {
      return await Promise.resolve(this._fn(task, kwargs));
    } else {
      return await Promise.resolve((this._fn as any)(kwargs));
    }
  }

  /**
   * Handles the tool response.
   * @internal
   */
  public async _handle_tool_response(
    task: TaskHandle | SessionHandle,
    event_id: string,
    response: any
  ): Promise<void> {
    const client = (task as any)._client as SmoothClient;

    if (response instanceof ToolCallError) {
      await client._send_task_event(task.id(), {
        id: event_id,
        name: 'tool_call',
        payload: {
          code: 400,
          output: String(response),
        },
      });
    } else if (response instanceof Error) {
      await client._send_task_event(task.id(), {
        id: event_id,
        name: 'tool_call',
        payload: {
          code: this._essential ? 500 : 400,
          output: this._error_message || String(response),
        },
      });
      if (this._essential) {
        throw response;
      }
    } else {
      await client._send_task_event(task.id(), {
        id: event_id,
        name: 'tool_call',
        payload: {
          code: 200,
          output: response,
        },
      });
    }
  }

  /**
   * Invokes the tool.
   * @internal
   */
  public async __call__(task: TaskHandle | SessionHandle, event_id: string, kwargs: Record<string, any>): Promise<any> {
    try {
      const response = await this._run_fn(task, kwargs);
      await this._handle_tool_response(task, event_id, response);
    } catch (e) {
      await this._handle_tool_response(task, event_id, e);
    }
  }
}

// --- Handles ---

/**
 * A handle to an interactive browser session.
 * @deprecated Use SessionHandle instead.
 */
export class BrowserSessionHandle {
  private browserSession: BrowserSessionResponse;

  constructor(browserSession: BrowserSessionResponse) {
    this.browserSession = browserSession;
  }

  /**
   * Returns the profile ID for the browser session.
   */
  public profileId(): string {
    return this.browserSession.profile_id;
  }

  /**
   * (Deprecated) Returns the session ID.
   * @deprecated Use `profileId()` instead.
   */
  public sessionId(): string {
    console.warn("'sessionId()' is deprecated, use 'profileId()' instead");
    return this.profileId();
  }

  /**
   * Returns the live URL for the browser session.
   */
  public liveUrl(interactive: boolean = true, embed: boolean = false): string | null {
    if (this.browserSession.live_url) {
      return _encode_url(this.browserSession.live_url, interactive, embed);
    }
    return null;
  }

  /**
   * Returns the live ID for the browser session.
   */
  public liveId(): string | null {
    return this.browserSession.live_id;
  }
}

/**
 * An asynchronous handle to a running task.
 */
export class TaskHandle {
  protected _client: SmoothClient;
  protected _id: string;
  protected _taskResponse: TaskResponse | null = null;
  protected _tools: Map<string, SmoothTool> = new Map();

  // Polling state
  protected _isAlive: number = 0;
  protected _pollInterval: number = 1000; // ms
  protected _lastEventT: number = 0;
  protected _eventFutures: Map<string, { resolve: (value: any) => void; reject: (error: any) => void }> = new Map();
  protected _toolTasks: Map<string, Promise<any>> = new Map();
  protected _pollerAbortController: AbortController | null = null;

  constructor(taskId: string, client: SmoothClient, tools?: SmoothTool[] | null) {
    this._id = taskId;
    this._client = client;
    if (tools) {
      for (const tool of tools) {
        this._tools.set(tool.name, tool);
      }
    }
  }

  /**
   * Returns the task ID.
   */
  public id(): string {
    return this._id;
  }

  /**
   * Stops (cancels) the running task.
   * @deprecated stop is deprecated
   */
  @deprecated('stop is deprecated')
  public async stop(): Promise<void> {
    await this._client._delete_task(this._id);
  }

  /**
   * Waits for the task to complete and returns the result.
   * @param timeout Maximum time to wait in seconds. If null, waits indefinitely.
   * @param poll_interval Time to wait between polls in seconds. (deprecated)
   * @returns The completed task response.
   */
  public async result(timeout: number | null = null, poll_interval?: number): Promise<TaskResponse> {
    if (this._taskResponse && !['running', 'waiting'].includes(this._taskResponse.status)) {
      return this._taskResponse;
    }

    if (timeout !== null && timeout < 1) {
      throw new ValueError('Timeout must be at least 1 second.');
    }

    if (poll_interval !== undefined) {
      console.warn('poll_interval is deprecated.');
    }

    const startTime = Date.now();

    await this._connect();
    try {
      while (timeout === null || Date.now() - startTime < timeout * 1000) {
        if (this._taskResponse && !['running', 'waiting'].includes(this._taskResponse.status)) {
          return this._taskResponse;
        }
        await sleep(200);
      }
      throw new TimeoutError(`Task ${this.id()} did not complete within ${timeout} seconds.`);
    } finally {
      this._disconnect();
    }
  }

  /**
   * Returns the live URL for the task, polling if necessary.
   * @param interactive Whether the live view should be interactive.
   * @param embed Whether the live view should be embedded.
   * @param timeout Maximum time to wait in seconds. If null, waits indefinitely.
   * @returns The live URL string.
   */
  public async live_url(
    interactive: boolean = false,
    embed: boolean = false,
    timeout: number | null = null
  ): Promise<string> {
    if (this._taskResponse?.live_url) {
      return _encode_url(this._taskResponse.live_url, interactive, embed);
    }

    const startTime = Date.now();
    await this._connect();
    try {
      while (timeout === null || Date.now() - startTime < timeout * 1000) {
        if (this._taskResponse?.live_url) {
          return _encode_url(this._taskResponse.live_url, interactive, embed);
        }
        await sleep(200);
      }
      throw new TimeoutError(`Live URL not available for task ${this.id()}.`);
    } finally {
      this._disconnect();
    }
  }

  /**
   * Returns the recording URL for the task, polling if necessary.
   * @param timeout Maximum time to wait in seconds. If null, waits indefinitely.
   * @returns The recording URL string.
   */
  public async recording_url(timeout: number | null = 30): Promise<string> {
    if (this._taskResponse?.recording_url !== null && this._taskResponse?.recording_url !== undefined) {
      return this._taskResponse.recording_url;
    }

    const startTime = Date.now();
    await this._connect();
    try {
      while (timeout === null || Date.now() - startTime < timeout * 1000) {
        if (this._taskResponse?.recording_url !== null && this._taskResponse?.recording_url !== undefined) {
          if (!this._taskResponse.recording_url) {
            throw new ApiError(
              404,
              `Recording URL not available for task ${this.id()}. Set \`enable_recording=True\` when creating the task to enable it.`
            );
          }
          return this._taskResponse.recording_url;
        }
        await sleep(200);
      }

      if (this._taskResponse && ['waiting', 'running'].includes(this._taskResponse.status)) {
        throw new BadRequestError(`Recording URL not available for task ${this.id()} while it is still running.`);
      }
      throw new TimeoutError(`Recording URL not available for task ${this.id()}.`);
    } finally {
      this._disconnect();
    }
  }

  /**
   * Returns the downloads URL for the task, polling if necessary.
   * @param timeout Maximum time to wait in seconds. If null, waits indefinitely.
   * @returns The downloads URL string.
   */
  public async downloads_url(timeout: number | null = 30): Promise<string> {
    if (this._taskResponse?.downloads_url !== null && this._taskResponse?.downloads_url !== undefined) {
      return this._taskResponse.downloads_url;
    }

    const startTime = Date.now();
    await this._connect();
    try {
      while (timeout === null || Date.now() - startTime < timeout * 1000) {
        if (this._taskResponse && !['waiting', 'running'].includes(this._taskResponse.status)) {
          const taskResponse = await this._client._get_task(this.id(), { downloads: 'true' });
          if (taskResponse.downloads_url !== null && taskResponse.downloads_url !== undefined) {
            if (!taskResponse.downloads_url) {
              throw new ApiError(
                404,
                `Downloads URL not available for task ${this.id()}. Make sure the task downloaded files during its execution.`
              );
            }
            return taskResponse.downloads_url;
          }
          await sleep(800);
        }
        await sleep(200);
      }

      if (this._taskResponse && ['waiting', 'running'].includes(this._taskResponse.status)) {
        throw new BadRequestError(`Downloads URL not available for task ${this.id()} while it is still running.`);
      }
      throw new TimeoutError(`Downloads URL not available for task ${this.id()}.`);
    } finally {
      this._disconnect();
    }
  }

  // --- Action Methods ---

  /**
   * Navigates to the given URL.
   * @param url The URL to navigate to.
   */
  public async goto(url: string): Promise<ActionGotoResponse> {
    const event: TaskEvent = {
      name: 'browser_action',
      payload: {
        name: 'goto',
        input: { url },
      },
    };
    const result = await this._send_event(event, true);
    return result || {};
  }

  /**
   * Extracts data from the current page.
   * @param schema The schema describing the data to extract.
   * @param prompt Optional prompt for extraction.
   */
  public async extract(schema: Record<string, any>, prompt?: string | null): Promise<ActionExtractResponse> {
    const event: TaskEvent = {
      name: 'browser_action',
      payload: {
        name: 'extract',
        input: {
          schema,
          prompt,
        },
      },
    };
    const result = await this._send_event(event, true);
    return result || { data: null };
  }

  /**
   * Executes JavaScript code in the browser context.
   * @param code The JavaScript code to execute.
   * @param args Optional arguments to pass to the code.
   */
  public async evaluate_js(code: string, args?: Record<string, any> | null): Promise<ActionEvaluateJSResponse> {
    const event: TaskEvent = {
      name: 'browser_action',
      payload: {
        name: 'evaluate_js',
        input: {
          js: code,
          args,
        },
      },
    };
    const result = await this._send_event(event, true);
    return result || { result: null };
  }

  // --- Private Methods ---

  /**
   * Sends an event to the running task.
   * @internal
   */
  protected async _send_event(event: TaskEvent, has_result: boolean = false): Promise<any | null> {
    event.id = event.id || nanoid();

    if (has_result) {
      const eventId = event.id;
      const promise = new Promise<any>((resolve, reject) => {
        this._eventFutures.set(eventId, { resolve, reject });
      });

      await this._client._send_task_event(this._id, event);
      return await promise;
    } else {
      await this._client._send_task_event(this._id, event);
      return null;
    }
  }

  /**
   * Connects to the task for polling.
   * @internal
   */
  protected async _connect(): Promise<void> {
    this._isAlive += 1;

    if (this._isAlive !== 1) {
      return;
    }

    this._taskResponse = await this._client._get_task(this.id(), { event_t: String(this._lastEventT) });

    this._pollerAbortController = new AbortController();
    const signal = this._pollerAbortController.signal;

    const poller = async () => {
      while (this._isAlive > 0 && !signal.aborted) {
        await sleep(this._pollInterval);

        if (signal.aborted) break;

        try {
          const taskResponse = await this._client._get_task(this.id(), { event_t: String(this._lastEventT) });
          this._taskResponse = taskResponse;

          if (taskResponse.events) {
            const lastEvent = taskResponse.events[taskResponse.events.length - 1];
            if (lastEvent?.timestamp) {
              this._lastEventT = lastEvent.timestamp;
            }

            for (const event of taskResponse.events) {
              if (event.name === 'tool_call') {
                const toolName = event.payload?.name;
                const tool = this._tools.get(toolName);
                if (tool && event.id) {
                  const toolTask = tool.__call__(this, event.id, event.payload?.input || {});
                  this._toolTasks.set(event.id, toolTask);
                  toolTask.finally(() => {
                    this._toolTasks.delete(event.id!);
                  });
                }
              } else if (event.name === 'browser_action' && event.id) {
                const future = this._eventFutures.get(event.id);
                if (future) {
                  this._eventFutures.delete(event.id);
                  const code = event.payload?.code;
                  if (code === 200) {
                    future.resolve(event.payload?.output);
                  } else if (code === 400) {
                    future.reject(new ToolCallError(event.payload?.output || 'Unknown error.'));
                  } else if (code === 500) {
                    future.reject(new ValueError(event.payload?.output || 'Unknown error.'));
                  }
                }
              }
            }
          }

          if (!['running', 'waiting'].includes(taskResponse.status)) {
            // Cancel all pending futures
            for (const [, future] of this._eventFutures) {
              future.reject(new Error('Task completed'));
            }
            this._eventFutures.clear();
            break;
          }
        } catch (error) {
          if (!signal.aborted) {
            console.error('Polling error:', error);
          }
        }
      }
    };

    // Start poller in background
    poller().catch((error) => {
      if (!signal.aborted) {
        console.error('Poller failed:', error);
      }
    });
  }

  /**
   * Disconnects from the task polling.
   * @internal
   */
  protected _disconnect(): void {
    this._isAlive = this._isAlive < 1 ? 0 : this._isAlive - 1;
    if (this._isAlive === 0 && this._pollerAbortController) {
      this._pollerAbortController.abort();
      this._pollerAbortController = null;
    }
  }

  // --- Deprecated Methods ---

  /**
   * Executes JavaScript code in the browser context.
   * @deprecated Use evaluate_js instead.
   */
  @deprecated('Use evaluate_js instead')
  public async exec_js(code: string, args?: Record<string, any> | null): Promise<any> {
    return this.evaluate_js(code, args);
  }
}

/**
 * A handle to an open browser session that supports running multiple tasks.
 */
export class SessionHandle extends TaskHandle {
  constructor(taskId: string, client: SmoothClient, tools?: SmoothTool[] | null) {
    super(taskId, client, tools);
  }

  /**
   * Use the session as a disposable resource (similar to Python's context manager).
   * @param callback The function to execute within the session context.
   * @returns The result of the callback.
   */
  public async use<T>(callback: (session: SessionHandle) => Promise<T>): Promise<T> {
    await this._connect();
    try {
      return await callback(this);
    } catch (error) {
      await this.close(true);
      throw error;
    } finally {
      await this.close(false);
      this._disconnect();
    }
  }

  /**
   * Closes the session.
   * @param force If true, forcefully closes the session. Otherwise, gracefully closes.
   */
  public async close(force: boolean = true): Promise<void> {
    if (!force) {
      const event: TaskEvent = {
        name: 'browser_action',
        payload: {
          name: 'close',
        },
      };
      await this._send_event(event, false);
    } else {
      await this._client._delete_task(this._id);
    }
  }

  /**
   * Runs a task within the session.
   * @param task The task description to run.
   * @param max_steps Maximum number of steps the agent can take.
   * @param response_model Optional schema describing the desired output structure.
   * @param url Optional URL to navigate to before running the task.
   * @param metadata Optional metadata to pass to the agent.
   */
  public async run_task(
    task: string,
    max_steps: number = 32,
    response_model?: Record<string, any> | null,
    url?: string | null,
    metadata?: Record<string, any> | null
  ): Promise<ActionRunTaskResponse> {
    const event: TaskEvent = {
      name: 'browser_action',
      payload: {
        name: 'run_task',
        input: {
          task,
          max_steps,
          response_model,
          url,
          metadata,
        },
      },
    };
    const result = await this._send_event(event, true);
    return result || { output: null };
  }
}

// --- client ---

/**
 * Options for the SmoothClient constructor.
 */
export interface SmoothClientOptions {
  api_key?: string;
  base_url?: string;
  api_version?: string;
  timeout?: number;
}

export class SmoothClient {
  private axios_instance: AxiosInstance;
  private base_url: string;

  constructor(options: SmoothClientOptions = {}) {
    const { api_key, base_url = BASE_URL, api_version = 'v1', timeout = 30000 } = options;

    const final_api_key = api_key ?? process.env.CIRCLEMIND_API_KEY;
    if (!final_api_key) {
      throw new ValueError('API key is required. Provide it directly or set CIRCLEMIND_API_KEY environment variable.');
    }

    if (!base_url) {
      throw new ValueError('Base URL cannot be empty.');
    }

    this.base_url = `${base_url.replace(/\/$/, '')}/${api_version}`;
    this.axios_instance = axios.create({
      baseURL: this.base_url,
      headers: {
        apikey: final_api_key,
        'User-Agent': `smooth-typescript-sdk/${SDK_VERSION}`,
        'Content-Type': 'application/json',
      },
      timeout: timeout,
    });
  }

  /**
   * Generic request helper to handle response unwrapping and error conversion.
   * @internal
   */
  private async _request<T>(
    method: 'get' | 'post' | 'delete' | 'put',
    url: string,
    data?: any,
    config: Record<string, any> = {}
  ): Promise<T> {
    try {
      let response: AxiosResponse<ApiResponse<T>>;
      if (method === 'get') {
        response = await this.axios_instance.get(url, config);
      } else if (method === 'post') {
        response = await this.axios_instance.post(url, data, config);
      } else if (method === 'put') {
        response = await this.axios_instance.put(url, data, config);
      } else {
        // 'delete'
        response = await this.axios_instance.delete(url, config);
      }
      // Assumes all successful responses are wrapped in {"r": ...}
      // Handle 2xx responses that might not have 'r' (like delete)
      if (response.status >= 200 && response.status < 300) {
        if (response.data && 'r' in response.data) {
          return response.data.r;
        }
        // For delete or other 2xx responses without 'r'
        return response.data as T;
      }
      // This part might not be reached if axios throws for non-2xx
      // but serves as a fallback.
      throw new ApiError(response.status, response.statusText, response.data);
    } catch (error) {
      if (axios.isAxiosError(error)) {
        const axiosError = error as AxiosError<any>;
        const status = axiosError.response?.status ?? 0;
        let detail = axiosError.message;
        let responseData = null;

        if (axiosError.response?.data) {
          responseData = axiosError.response.data;
          detail = axiosError.response.data.detail ?? axiosError.message;
        }

        // Handle successful delete (2xx) that might be caught as error
        // if response.data is not JSON or doesn't have 'r'
        if (status >= 200 && status < 300) {
          return (responseData ?? {}) as T;
        }

        throw new ApiError(status, detail, responseData);
      }
      // Fallback for non-Axios errors
      throw new ApiError(0, (error as Error).message);
    }
  }

  /**
   * Process certificates, converting binary IO to base64-encoded strings.
   * @internal
   */
  private _process_certificates(
    certificates: Certificate[] | null | undefined
  ): ProcessedCertificate[] | null | undefined {
    if (!certificates) {
      return null;
    }

    return certificates.map((cert) => {
      let file_content: string;
      if (Buffer.isBuffer(cert.file)) {
        file_content = cert.file.toString('base64');
      } else if (typeof cert.file === 'string') {
        file_content = cert.file; // Assumes it's already base64
      } else {
        throw new ValueError('Certificate file must be a Buffer or a base64 string.');
      }

      const processed_cert: ProcessedCertificate = {
        file: file_content,
      };
      if (cert.password) {
        processed_cert.password = cert.password;
      }
      if (cert.filters) {
        processed_cert.filters = cert.filters;
      }
      return processed_cert;
    });
  }

  /**
   * Process custom tools to extract their signatures.
   * @internal
   */
  private _process_custom_tools(
    custom_tools: (SmoothTool | ToolSignature)[] | null | undefined
  ): { signatures: ToolSignature[] | null; tools: SmoothTool[] | null } {
    if (!custom_tools) {
      return { signatures: null, tools: null };
    }

    const signatures: ToolSignature[] = [];
    const tools: SmoothTool[] = [];

    for (const tool of custom_tools) {
      if (tool instanceof SmoothTool) {
        signatures.push(tool.signature);
        tools.push(tool);
      } else {
        signatures.push(tool);
      }
    }

    return { signatures, tools: tools.length > 0 ? tools : null };
  }

  /** @internal */
  public async _submit_task(payload: TaskRequestPayload): Promise<TaskResponse> {
    return this._request<TaskResponse>('post', '/task', payload);
  }

  /** @internal */
  public async _get_task(task_id: string, query_params?: Record<string, string>): Promise<TaskResponse> {
    if (!task_id) {
      throw new ValueError('Task ID cannot be empty.');
    }
    return this._request<TaskResponse>('get', `/task/${task_id}`, undefined, { params: query_params });
  }

  /** @internal */
  public async _delete_task(task_id: string): Promise<void> {
    if (!task_id) {
      throw new ValueError('Task ID cannot be empty.');
    }
    // Delete requests might not return the 'r' wrapper,
    // and _request handles non-'r' 2xx responses.
    await this._request<void>('delete', `/task/${task_id}`);
  }

  /** @internal */
  public async _send_task_event(task_id: string, event: TaskEvent): Promise<TaskEventResponse> {
    if (!task_id) {
      throw new ValueError('Task ID cannot be empty.');
    }
    return this._request<TaskEventResponse>('post', `/task/${task_id}/event`, event);
  }

  /**
   * Opens a browser session that can be used to run multiple tasks.
   * @param options The session configuration options.
   * @returns A handle to the session.
   */
  public async session(options: SessionOptions = {}): Promise<SessionHandle> {
    const taskHandle = await this.run({
      task: null as any, // Opens a blank browser
      url: options.url,
      files: options.files,
      agent: options.agent ?? 'smooth',
      device: options.device ?? 'mobile',
      allowed_urls: options.allowed_urls,
      enable_recording: options.enable_recording ?? true,
      profile_id: options.profile_id,
      profile_read_only: options.profile_read_only ?? false,
      stealth_mode: options.stealth_mode ?? false,
      proxy_server: options.proxy_server,
      proxy_username: options.proxy_username,
      proxy_password: options.proxy_password,
      certificates: options.certificates,
      use_adblock: options.use_adblock ?? true,
      additional_tools: options.additional_tools,
      custom_tools: options.custom_tools,
      experimental_features: options.experimental_features,
      extensions: options.extensions,
    });

    return new SessionHandle(taskHandle.id(), this, Array.from(taskHandle['_tools'].values()));
  }

  /**
   * Runs a task and returns a handle to the task asynchronously.
   * @param options The task configuration options.
   * @returns A handle to the running task.
   */
  public async run(options: RunTaskOptions): Promise<TaskHandle> {
    if (options.session_id && !options.profile_id) {
      console.warn("'session_id' is deprecated, use 'profile_id' instead");
    }

    const profile_id = options.profile_id ?? options.session_id;

    // Process certificates
    const processed_certificates = this._process_certificates(options.certificates);

    // Process custom tools
    const { signatures, tools } = this._process_custom_tools(options.custom_tools);

    const payload: TaskRequestPayload = {
      task: options.task,
      response_model: options.response_model,
      url: options.url,
      metadata: options.metadata,
      files: options.files,
      agent: options.agent ?? 'smooth',
      max_steps: options.max_steps ?? 32,
      device: options.device ?? 'mobile',
      allowed_urls: options.allowed_urls,
      enable_recording: options.enable_recording ?? true,
      profile_id: profile_id,
      session_id: profile_id, // Add deprecated session_id for retro-compatibility
      profile_read_only: options.profile_read_only ?? false,
      stealth_mode: options.stealth_mode ?? false,
      proxy_server: options.proxy_server,
      proxy_username: options.proxy_username,
      proxy_password: options.proxy_password,
      certificates: processed_certificates,
      use_adblock: options.use_adblock ?? true,
      additional_tools: options.additional_tools,
      custom_tools: signatures,
      experimental_features: options.experimental_features,
      extensions: options.extensions,
    };

    const initialResponse = await this._submit_task(payload);
    return new TaskHandle(initialResponse.id, this, tools);
  }

  /**
   * Creates a custom tool that can be registered with the client.
   * @param name The name of the tool.
   * @param description A brief description of the tool.
   * @param inputs The input parameters for the tool.
   * @param output A description of the output produced by the tool.
   * @param essential Whether the tool is essential (errors are fatal).
   * @param error_message Optional custom error message.
   * @returns A decorator function that creates a SmoothTool.
   */
  public tool(
    name: string,
    description: string,
    inputs: Record<string, any>,
    output: string,
    essential: boolean = true,
    error_message?: string | null
  ): (fn: ToolFunction) => SmoothTool {
    return (fn: ToolFunction) => {
      return new SmoothTool({
        signature: { name, description, inputs, output },
        fn,
        essential,
        error_message,
      });
    };
  }

  // --- Profile Methods ---

  /**
   * Creates a new browser profile.
   * @param profile_id Optional custom ID for the profile.
   * @returns The created browser profile.
   */
  public async create_profile(profile_id?: string | null): Promise<ProfileResponse> {
    return this._request<ProfileResponse>('post', '/profile', { id: profile_id });
  }

  /**
   * Lists all browser profiles for the user.
   * @returns A list of existing browser profiles.
   */
  public async list_profiles(): Promise<ProfileResponse[]> {
    return this._request<ProfileResponse[]>('get', '/profile');
  }

  /**
   * Deletes a browser profile.
   * @param profile_id The ID of the profile to delete.
   */
  public async delete_profile(profile_id: string): Promise<void> {
    await this._request<void>('delete', `/profile/${profile_id}`);
  }

  // --- File Upload Methods ---

  /**
   * Uploads a file and returns the file ID.
   * @param file The file content as a Buffer or Readable stream.
   * @param name The name of the file.
   * @param purpose Optional short description of the file's purpose.
   * @returns The file ID assigned to the uploaded file.
   */
  public async upload_file(file: Buffer | Readable, name: string, purpose?: string): Promise<UploadFileResponse> {
    if (!name) {
      throw new ValueError('File name must be provided.');
    }

    const form = new FormData();
    form.append('file', file, name);
    if (purpose) {
      form.append('file_purpose', purpose);
    }

    try {
      const response = await this.axios_instance.post<ApiResponse<UploadFileResponse>>('/file', form, {
        headers: form.getHeaders(), // Let form-data set the Content-Type
      });
      return response.data.r;
    } catch (error) {
      if (axios.isAxiosError(error)) {
        const axiosError = error as AxiosError<any>;
        const status = axiosError.response?.status ?? 0;
        const detail = axiosError.response?.data?.detail ?? axiosError.message;
        const responseData = axiosError.response?.data ?? null;
        throw new ApiError(status, detail, responseData);
      }
      throw new ApiError(0, (error as Error).message);
    }
  }

  /**
   * Deletes a file by its ID.
   * @param file_id The ID of the file to delete.
   */
  public async delete_file(file_id: string): Promise<void> {
    await this._request<void>('delete', `/file/${file_id}`);
  }

  // --- Extension Methods ---

  /**
   * Uploads an extension package (CRX/ZIP) and returns the extension ID.
   * @param file The extension file content as a Buffer or Readable stream.
   * @param name The file name for the extension.
   */
  public async upload_extension(file: Buffer | Readable, name: string): Promise<UploadExtensionResponse> {
    if (!name) {
      throw new ValueError('Extension file name must be provided.');
    }

    const form = new FormData();
    form.append('file', file, name);

    try {
      const response = await this.axios_instance.post<ApiResponse<UploadExtensionResponse>>(
        '/browser/extension',
        form,
        { headers: form.getHeaders() }
      );
      return response.data.r;
    } catch (error) {
      if (axios.isAxiosError(error)) {
        const axiosError = error as AxiosError<any>;
        const status = axiosError.response?.status ?? 0;
        const detail = axiosError.response?.data?.detail ?? axiosError.message;
        const responseData = axiosError.response?.data ?? null;
        throw new ApiError(status, detail, responseData);
      }
      throw new ApiError(0, (error as Error).message);
    }
  }

  /**
   * Lists all uploaded extensions for the user.
   */
  public async list_extensions(): Promise<ListExtensionsResponse> {
    const response = await this._request<ListExtensionsResponse>('get', '/browser/extension');
    return response;
  }

  /**
   * Deletes an extension by its ID.
   * @param extension_id The ID of the extension to delete.
   */
  public async delete_extension(extension_id: string): Promise<void> {
    await this._request<void>('delete', `/browser/extension/${extension_id}`);
  }

  /**
   * Closes the client. (In axios, this is a no-op but good for API consistency).
   */
  public async close(): Promise<void> {
    // Axios doesn't require an explicit close for its connection pool
    // This method is here for API compatibility with the Python SDK's close/aexit
  }

  // --- Deprecated Methods ---

  /**
   * Opens an interactive browser instance asynchronously.
   * @param options The session configuration options.
   * @returns The browser session handle.
   * @deprecated Use `session()` instead.
   */
  @deprecated('Use session() instead')
  public async open_session(options: OpenSessionOptions = {}): Promise<BrowserSessionHandle> {
    if (options.session_id && !options.profile_id) {
      console.warn("'session_id' is deprecated, use 'profile_id' instead");
    }

    const profile_id = options.profile_id ?? options.session_id;

    const payload: BrowserSessionRequestPayload = {
      profile_id: profile_id,
      session_id: profile_id, // Add deprecated session_id for retro-compatibility
      live_view: options.live_view ?? true,
      device: options.device ?? 'desktop',
      url: options.url,
      proxy_server: options.proxy_server,
      proxy_username: options.proxy_username,
      proxy_password: options.proxy_password,
    };

    const response = await this._request<BrowserSessionResponse>('post', '/browser/session', payload);
    return new BrowserSessionHandle(response);
  }

  /**
   * Closes a browser session.
   * @param live_id The live ID of the session to close.
   * @deprecated
   */
  @deprecated('')
  public async close_session(live_id: string): Promise<void> {
    await this._request<void>('delete', `/browser/session/${live_id}`);
  }

  /**
   * (Deprecated) Lists all browser profiles for the user.
   * @deprecated Use `list_profiles` instead.
   */
  @deprecated('Use list_profiles instead')
  public async list_sessions(): Promise<BrowserProfilesResponse> {
    const response = await this._request<BrowserProfilesResponse>('get', '/browser/profile');
    // Add deprecated session_ids for retro-compatibility
    if (response.profile_ids) {
      response.session_ids = response.profile_ids;
    }
    return response;
  }

  /**
   * (Deprecated) Deletes a browser profile.
   * @param session_id The ID of the profile to delete.
   * @deprecated Use `delete_profile` instead.
   */
  @deprecated('Use delete_profile instead')
  public async delete_session(session_id: string): Promise<void> {
    return this.delete_profile(session_id);
  }
}
