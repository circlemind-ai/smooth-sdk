import axios, { AxiosInstance, AxiosError, AxiosResponse } from 'axios';
import FormData from 'form-data';
import { Readable } from 'stream';
import { URL } from 'url';

// --- Constants ---
const BASE_URL = 'https://api.smooth.sh/api/';

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
  [key: string]: any; // Allow extra properties as in the Python model
}

/**
 * Interface for the raw task request payload sent to the API.
 * @internal
 */
interface TaskRequestPayload {
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
  experimental_features?: Record<string, any> | null;
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
  experimental_features?: Record<string, any> | null;
}

/**
 * Interface for the raw browser session request payload.
 * @internal
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

export interface UploadFileResponse {
  id: string;
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

// --- Handles ---

/**
 * A handle to an interactive browser session.
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
  private _client: SmoothClient;
  private _id: string;
  private _taskResponse: TaskResponse | null = null;

  constructor(taskId: string, client: SmoothClient) {
    this._id = taskId;
    this._client = client;
  }

  /**
   * Returns the task ID.
   */
  public id(): string {
    return this._id;
  }

  /**
   * Stops (cancels) the running task.
   */
  public async stop(): Promise<void> {
    await this._client._delete_task(this._id);
  }

  /**
   * Waits for the task to complete and returns the result.
   * @param timeout Maximum time to wait in seconds. If null, waits indefinitely.
   * @param poll_interval Time to wait between polls in seconds.
   * @returns The completed task response.
   */
  public async result(timeout: number | null = null, poll_interval: number = 1): Promise<TaskResponse> {
    if (this._taskResponse && !['running', 'waiting'].includes(this._taskResponse.status)) {
      return this._taskResponse;
    }

    if (timeout !== null && timeout < 1) {
      throw new ValueError('Timeout must be at least 1 second.');
    }
    if (poll_interval < 0.1) {
      throw new ValueError('Poll interval must be at least 100 milliseconds.');
    }

    const startTime = Date.now();
    const pollIntervalMs = poll_interval * 1000;

    while (timeout === null || Date.now() - startTime < timeout * 1000) {
      const taskResponse = await this._client._get_task(this.id());
      this._taskResponse = taskResponse;
      if (!['running', 'waiting'].includes(taskResponse.status)) {
        return taskResponse;
      }
      await sleep(pollIntervalMs);
    }

    throw new TimeoutError(`Task ${this.id()} did not complete within ${timeout} seconds.`);
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
    while (timeout === null || Date.now() - startTime < timeout * 1000) {
      const taskResponse = await this._client._get_task(this.id());
      this._taskResponse = taskResponse;
      if (taskResponse.live_url) {
        return _encode_url(taskResponse.live_url, interactive, embed);
      }
      await sleep(1000); // Poll every second
    }

    const errorMsg = timeout ? `within ${timeout} seconds` : 'indefinitely';
    throw new TimeoutError(`Live URL not available for task ${this.id()} ${errorMsg}.`);
  }

  /**
   * Returns the recording URL for the task, polling if necessary.
   * @param timeout Maximum time to wait in seconds. If null, waits indefinitely.
   * @returns The recording URL string.
   */
  public async recording_url(timeout: number | null = null): Promise<string> {
    if (this._taskResponse?.recording_url !== null && this._taskResponse?.recording_url !== undefined) {
      return this._taskResponse.recording_url;
    }

    const startTime = Date.now();
    while (timeout === null || Date.now() - startTime < timeout * 1000) {
      const taskResponse = await this._client._get_task(this.id());
      this._taskResponse = taskResponse;
      if (taskResponse.recording_url !== null && taskResponse.recording_url !== undefined) {
        if (!taskResponse.recording_url) {
          throw new ApiError(
            404,
            `Recording URL not available for task ${this.id()}. Set \`enable_recording=True\` when creating the task to enable it.`
          );
        }
        return taskResponse.recording_url;
      }
      await sleep(1000); // Poll every second
    }

    const errorMsg = timeout ? `within ${timeout} seconds` : 'indefinitely';
    throw new TimeoutError(`Recording URL not available for task ${this.id()} ${errorMsg}.`);
  }

  /**
   * Returns the downloads URL for the task, polling if necessary.
   * @param timeout Maximum time to wait in seconds. If null, waits indefinitely.
   * @returns The downloads URL string.
   */
  public async downloads_url(timeout: number | null = null): Promise<string> {
    if (this._taskResponse?.downloads_url !== null && this._taskResponse?.downloads_url !== undefined) {
      return this._taskResponse.downloads_url;
    }

    const startTime = Date.now();
    while (timeout === null || Date.now() - startTime < timeout * 1000) {
      const taskResponse = await this._client._get_task(this.id(), { downloads: 'true' });
      this._taskResponse = taskResponse;
      if (taskResponse.downloads_url !== null && taskResponse.downloads_url !== undefined) {
        if (!taskResponse.downloads_url) {
          throw new ApiError(
            404,
            `Downloads URL not available for task ${this.id()}. Make sure the task downloaded files during its execution.`
          );
        }
        return taskResponse.downloads_url;
      }
      await sleep(1000); // Poll every second
    }

    const errorMsg = timeout ? `within ${timeout} seconds` : 'indefinitely';
    throw new TimeoutError(`Downloads URL not available for task ${this.id()} ${errorMsg}.`);
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
        'User-Agent': 'smooth-typescript-sdk/0.2.5', // Match Python version
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
    method: 'get' | 'post' | 'delete',
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
      return certificates; // Handles null and undefined
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
      experimental_features: options.experimental_features,
    };

    const initialResponse = await this._submit_task(payload);
    return new TaskHandle(initialResponse.id, this);
  }

  /**
   * Opens an interactive browser instance asynchronously.
   * @param options The session configuration options.
   * @returns The browser session handle.
   */
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
   */
  public async close_session(live_id: string): Promise<void> {
    await this._request<void>('delete', `/browser/session/${live_id}`);
  }

  /**
   * Lists all browser profiles for the user.
   * @returns A list of existing browser profiles.
   */
  public async list_profiles(): Promise<BrowserProfilesResponse> {
    const response = await this._request<BrowserProfilesResponse>('get', '/browser/profile');
    // Add deprecated session_ids for retro-compatibility
    if (response.profile_ids) {
      response.session_ids = response.profile_ids;
    }
    return response;
  }

  /**
   * (Deprecated) Lists all browser profiles for the user.
   * @deprecated Use `list_profiles` instead.
   */
  public async list_sessions(): Promise<BrowserProfilesResponse> {
    console.warn("'list_sessions' is deprecated, use 'list_profiles' instead");
    return this.list_profiles();
  }

  /**
   * Deletes a browser profile.
   * @param profile_id The ID of the profile to delete.
   */
  public async delete_profile(profile_id: string): Promise<void> {
    await this._request<void>('delete', `/browser/profile/${profile_id}`);
  }

  /**
   * (Deprecated) Deletes a browser profile.
   * @param session_id The ID of the profile to delete.
   * @deprecated Use `delete_profile` instead.
   */
  public async delete_session(session_id: string): Promise<void> {
    console.warn("'delete_session' is deprecated, use 'delete_profile' instead");
    return this.delete_profile(session_id);
  }

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
      const response = await this.axios_instance.post<ApiResponse<UploadFileResponse>>(
        '/file',
        form,
        {
          headers: form.getHeaders(), // Let form-data set the Content-Type
        }
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
   * Deletes a file by its ID.
   * @param file_id The ID of the file to delete.
   */
  public async delete_file(file_id: string): Promise<void> {
    await this._request<void>('delete', `/file/${file_id}`);
  }

  /**
   * Closes the client. (In axios, this is a no-op but good for API consistency).
   */
  public async close(): Promise<void> {
    // Axios doesn't require an explicit close for its connection pool
    // This method is here for API compatibility with the Python SDK's close/aexit
  }
}