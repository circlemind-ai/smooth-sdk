export { SmoothClient } from "./client.js";
export type {
  ClientOptions,
  ProxyConfig,
  RunOptions,
  SessionOptions,
} from "./client.js";

export { TaskHandle } from "./handles/task-handle.js";
export { SessionHandle } from "./handles/session-handle.js";

export { SmoothTool } from "./tools.js";
export type { ToolOptions, ToolFunction } from "./tools.js";

export {
  ApiError,
  BadRequestError,
  SmoothTimeoutError as TimeoutError,
  ToolCallError,
} from "./errors.js";

export { Telemetry } from "./telemetry.js";

export type {
  DeviceType,
  TaskStatus,
  Agent,
  Certificate,
  ToolSignature,
  Secret,
  TaskEvent,
  TaskEventResponse,
  TaskRequest,
  TaskResponse,
  ProfileResponse,
  UploadFileResponse,
  UploadExtensionResponse,
  Extension,
  BaseActionResponse,
  ActionGotoResponse,
  ActionCloseResponse,
  ActionExtractResponse,
  ActionEvaluateJSResponse,
  ActionRunTaskResponse,
} from "./models/index.js";
