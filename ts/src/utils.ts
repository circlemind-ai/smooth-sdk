import type { Certificate } from "./models/types.js";

const LOG_LEVEL = (process.env.SMOOTH_LOG_LEVEL ?? "WARNING").toUpperCase();

const LEVELS: Record<string, number> = {
  DEBUG: 0,
  INFO: 1,
  WARNING: 2,
  WARN: 2,
  ERROR: 3,
};

const currentLevel = LEVELS[LOG_LEVEL] ?? 2;

export const logger = {
  debug: (...args: unknown[]) => {
    if (currentLevel <= 0) console.debug("[smooth]", ...args);
  },
  info: (...args: unknown[]) => {
    if (currentLevel <= 1) console.info("[smooth]", ...args);
  },
  warn: (...args: unknown[]) => {
    if (currentLevel <= 2) console.warn("[smooth]", ...args);
  },
  error: (...args: unknown[]) => {
    if (currentLevel <= 3) console.error("[smooth]", ...args);
  },
};

export function encodeUrl(
  url: string,
  interactive: boolean = true,
  embed: boolean = false,
): string {
  const parsed = new URL(url);
  parsed.searchParams.set("interactive", interactive ? "true" : "false");
  parsed.searchParams.set("embed", embed ? "true" : "false");
  return parsed.toString();
}

export function processCertificates(
  certificates: Array<Certificate | Record<string, unknown>> | null | undefined,
): Certificate[] | null {
  if (!certificates) return null;

  return certificates.map((cert) => {
    const processed = { ...("file" in cert ? cert : cert) } as Certificate;

    if (Buffer.isBuffer(processed.file)) {
      return {
        ...processed,
        file: processed.file.toString("base64"),
      };
    }

    if (typeof processed.file === "string") {
      return processed;
    }

    throw new TypeError(
      `Certificate file must be a string or Buffer, got ${typeof processed.file}`,
    );
  });
}

/**
 * Convert a camelCase object to snake_case for API wire format.
 */
export function toSnakeCase(
  obj: Record<string, unknown>,
): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(obj)) {
    const snakeKey = key.replace(
      /[A-Z]/g,
      (letter) => `_${letter.toLowerCase()}`,
    );
    result[snakeKey] = value;
  }
  return result;
}

/**
 * Convert a snake_case object to camelCase for TS consumption.
 */
export function toCamelCase(
  obj: Record<string, unknown>,
): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(obj)) {
    const camelKey = key.replace(/_([a-z])/g, (_, letter: string) =>
      letter.toUpperCase(),
    );
    result[camelKey] = value;
  }
  return result;
}
