import { z } from "zod";

// --- Enums ---

export const DeviceTypeSchema = z.enum(["desktop", "mobile", "desktop-lg"]);

export const TaskStatusSchema = z.enum([
  "waiting",
  "running",
  "done",
  "failed",
  "cancelled",
]);

export const AgentSchema = z.enum(["smooth", "smooth-lite"]);

// --- Component Schemas ---

export const CertificateSchema = z.object({
  file: z.union([z.string(), z.instanceof(Buffer)]),
  password: z.string().nullish(),
  filters: z.array(z.array(z.string())).nullish(),
});

export const ToolSignatureSchema = z.object({
  name: z.string(),
  description: z.string(),
  inputs: z.record(z.any()),
  output: z.string(),
});

export const SecretSchema = z.object({
  value: z.string(),
  allowed_urls: z.array(z.string()),
});

export const TaskEventSchema = z.object({
  name: z.string(),
  payload: z.record(z.any()),
  id: z.string().nullish(),
  timestamp: z.number().nullish(),
});

export const TaskEventResponseSchema = z.object({
  id: z.string(),
});

// --- Request Schemas ---

export const TaskRequestSchema = z.object({
  task: z.string().nullish(),
  response_model: z.record(z.any()).nullish(),
  url: z.string().nullish(),
  metadata: z
    .record(z.union([z.string(), z.number(), z.boolean()]))
    .nullish(),
  files: z.array(z.string()).nullish(),
  agent: AgentSchema.default("smooth"),
  max_steps: z.number().int().min(2).max(128).default(32),
  device: DeviceTypeSchema.default("desktop"),
  allowed_urls: z.array(z.string()).nullish(),
  enable_recording: z.boolean().default(true),
  profile_id: z.string().nullish(),
  profile_read_only: z.boolean().default(false),
  /** @deprecated ignored by the server. Use `use_stealth` instead (defaults to true). */
  stealth_mode: z.boolean().default(false),
  use_stealth: z.boolean().default(true),
  proxy_server: z.string().nullish(),
  proxy_username: z.string().nullish(),
  proxy_password: z.string().nullish(),
  certificates: z.array(CertificateSchema).nullish(),
  use_adblock: z.boolean().nullish().default(true),
  use_captcha_solver: z.boolean().nullish().default(true),
  additional_tools: z.record(z.record(z.any()).nullable()).nullish(),
  custom_tools: z.array(ToolSignatureSchema).nullish(),
  experimental_features: z.record(z.any()).nullish(),
  extensions: z.array(z.string()).nullish(),
  show_cursor: z.boolean().default(false),
});

// --- Response Schemas ---

export const TaskResponseSchema = z.object({
  id: z.string(),
  status: TaskStatusSchema,
  output: z.any().nullish(),
  credits_used: z.number().nullish(),
  device: DeviceTypeSchema.nullish(),
  live_url: z.string().nullish(),
  recording_url: z.string().nullish(),
  downloads_url: z.string().nullish(),
  created_at: z.number().nullish(),
  events: z.array(TaskEventSchema).nullish(),
});

export const ProfileResponseSchema = z.object({
  id: z.string(),
});

export const UploadFileResponseSchema = z.object({
  id: z.string(),
});

export const UploadExtensionResponseSchema = z.object({
  id: z.string(),
});

export const ExtensionSchema = z.object({
  id: z.string(),
  file_name: z.string(),
  creation_time: z.number(),
});

// --- Action Response Schemas ---

export const BaseActionResponseSchema = z.object({
  credits_used: z.number().default(0),
  duration: z.number().default(0),
});

export const ActionGotoResponseSchema = BaseActionResponseSchema;

export const ActionCloseResponseSchema = BaseActionResponseSchema.extend({
  output: z.boolean(),
});

export const ActionExtractResponseSchema = BaseActionResponseSchema.extend({
  output: z.any(),
});

export const ActionEvaluateJSResponseSchema = BaseActionResponseSchema.extend({
  output: z.any(),
});

export const ActionRunTaskResponseSchema = BaseActionResponseSchema.extend({
  output: z.any(),
});
