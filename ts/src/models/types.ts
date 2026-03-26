import { z } from "zod";
import {
  DeviceTypeSchema,
  TaskStatusSchema,
  AgentSchema,
  CertificateSchema,
  ToolSignatureSchema,
  SecretSchema,
  TaskEventSchema,
  TaskEventResponseSchema,
  TaskRequestSchema,
  TaskResponseSchema,
  ProfileResponseSchema,
  UploadFileResponseSchema,
  UploadExtensionResponseSchema,
  ExtensionSchema,
  BaseActionResponseSchema,
  ActionGotoResponseSchema,
  ActionCloseResponseSchema,
  ActionExtractResponseSchema,
  ActionEvaluateJSResponseSchema,
  ActionRunTaskResponseSchema,
} from "./schemas.js";

export type DeviceType = z.infer<typeof DeviceTypeSchema>;
export type TaskStatus = z.infer<typeof TaskStatusSchema>;
export type Agent = z.infer<typeof AgentSchema>;
export type Certificate = z.infer<typeof CertificateSchema>;
export type ToolSignature = z.infer<typeof ToolSignatureSchema>;
export type Secret = z.infer<typeof SecretSchema>;
export type TaskEvent = z.infer<typeof TaskEventSchema>;
export type TaskEventResponse = z.infer<typeof TaskEventResponseSchema>;
export type TaskRequest = z.infer<typeof TaskRequestSchema>;
export type TaskResponse = z.infer<typeof TaskResponseSchema>;
export type ProfileResponse = z.infer<typeof ProfileResponseSchema>;
export type UploadFileResponse = z.infer<typeof UploadFileResponseSchema>;
export type UploadExtensionResponse = z.infer<
  typeof UploadExtensionResponseSchema
>;
export type Extension = z.infer<typeof ExtensionSchema>;
export type BaseActionResponse = z.infer<typeof BaseActionResponseSchema>;
export type ActionGotoResponse = z.infer<typeof ActionGotoResponseSchema>;
export type ActionCloseResponse = z.infer<typeof ActionCloseResponseSchema>;
export type ActionExtractResponse = z.infer<typeof ActionExtractResponseSchema>;
export type ActionEvaluateJSResponse = z.infer<
  typeof ActionEvaluateJSResponseSchema
>;
export type ActionRunTaskResponse = z.infer<typeof ActionRunTaskResponseSchema>;
