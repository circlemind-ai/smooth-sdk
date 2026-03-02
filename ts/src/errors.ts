export class ApiError extends Error {
  readonly statusCode: number;
  readonly detail: string;
  readonly responseData: Record<string, unknown> | null;

  constructor(
    statusCode: number,
    detail: string,
    responseData?: Record<string, unknown> | null,
  ) {
    super(`API Error ${statusCode}: ${detail}`);
    this.name = "ApiError";
    this.statusCode = statusCode;
    this.detail = detail;
    this.responseData = responseData ?? null;
  }
}

export class BadRequestError extends Error {
  constructor(message?: string) {
    super(message);
    this.name = "BadRequestError";
  }
}

export class SmoothTimeoutError extends Error {
  constructor(message?: string) {
    super(message);
    this.name = "TimeoutError";
  }
}

export class ToolCallError extends Error {
  constructor(message?: string) {
    super(message);
    this.name = "ToolCallError";
  }
}

export { SmoothTimeoutError as TimeoutError };
