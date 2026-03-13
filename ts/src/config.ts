declare const __SDK_VERSION__: string;

export const BASE_URL = process.env.SMOOTH_BASE_URL ?? "https://api.smooth.sh/api/";

export const SDK_VERSION: string =
  typeof __SDK_VERSION__ !== "undefined" ? __SDK_VERSION__ : "0.0.0-dev";

export const USER_AGENT = `smooth-ts-sdk/${SDK_VERSION}`;
