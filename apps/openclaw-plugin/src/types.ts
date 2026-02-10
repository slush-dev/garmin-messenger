// OpenClaw SDK types — imported from the openclaw npm package (devDependency).
// Only Garmin-specific types and types not available from the SDK entry point
// are defined locally.

// ---------------------------------------------------------------------------
// Re-exports from openclaw/plugin-sdk (types available in the public entry)
// ---------------------------------------------------------------------------

export type {
  ChannelAccountSnapshot,
  ChannelAuthAdapter,
  ChannelCapabilities,
  ChannelConfigAdapter,
  ChannelConfigSchema,
  ChannelDirectoryAdapter,
  ChannelDirectoryEntry,
  ChannelDirectoryEntryKind,
  ChannelGatewayAdapter,
  ChannelGatewayContext,
  ChannelLogSink,
  ChannelMeta,
  ChannelOnboardingAdapter,
  ChannelOutboundAdapter,
  ChannelOutboundContext,
  ChannelPairingAdapter,
  ChannelPlugin,
  ChannelSecurityAdapter,
  ChannelSecurityContext,
  ChannelSecurityDmPolicy,
  ChannelSetupAdapter,
  ChannelSetupInput,
  ChannelStatusAdapter,
  OpenClawConfig,
  OpenClawPluginApi,
  PluginRuntime,
  ReplyPayload,
  RuntimeEnv,
  RuntimeLogger,
  WizardPrompter,
} from "openclaw/plugin-sdk";

// Value constant — defined locally to avoid bundling SDK runtime code.
export const DEFAULT_ACCOUNT_ID = "default";

// ---------------------------------------------------------------------------
// Types NOT in the SDK public entry point — kept locally
// ---------------------------------------------------------------------------

// ChannelAgentPromptAdapter exists in SDK internals but is not re-exported
// from the openclaw/plugin-sdk entry point.
export interface ChannelAgentPromptAdapter {
  messageToolHints?: (params: { cfg: Record<string, any>; accountId?: string | null }) => string[];
}

// Onboarding sub-types (ChannelOnboardingAdapter is in the SDK, but these
// context/result types used in method signatures are not re-exported).
export type ChannelOnboardingStatus = {
  channel: string;
  configured: boolean;
  statusLines: string[];
  selectionHint?: string;
  quickstartScore?: number;
};

export type ChannelOnboardingResult = {
  cfg: Record<string, any>;
  accountId?: string;
};

export type ChannelOnboardingConfigureContext = {
  cfg: Record<string, any>;
  runtime: import("openclaw/plugin-sdk").RuntimeEnv;
  prompter: import("openclaw/plugin-sdk").WizardPrompter;
  options?: Record<string, unknown>;
  accountOverrides: Partial<Record<string, string>>;
  shouldPromptAccountIds: boolean;
  forceAllowFrom: boolean;
};

export type ChannelOnboardingStatusContext = {
  cfg: Record<string, any>;
  options?: Record<string, unknown>;
  accountOverrides: Partial<Record<string, string>>;
};

// Outbound delivery result (not re-exported from SDK entry point).
export type OutboundDeliveryResult = {
  channel: string;
  messageId: string;
  chatId?: string;
  channelId?: string;
  roomId?: string;
  conversationId?: string;
  timestamp?: number;
  toJid?: string;
  pollId?: string;
  meta?: Record<string, unknown>;
};

// Agent tool result (originates from @mariozechner/pi-agent-core, not in SDK
// entry; the SDK's version uses TextContent | ImageContent union).
export type AgentToolResult = {
  content: Array<{ type: "text"; text: string } | { type: "image"; data: string; mimeType: string }>;
  details: unknown;
};

// Agent tool types — the SDK versions reference AgentTool from pi-agent-core.
// Keep local but match the SDK's required fields so the types are assignable.
export type ChannelAgentTool = {
  name: string;
  label: string;
  description: string;
  parameters: import("@sinclair/typebox").TSchema;
  execute: (toolCallId: string, args: unknown, signal?: AbortSignal, onUpdate?: unknown) => Promise<AgentToolResult>;
};

export type ChannelAgentToolFactory = (params: { cfg?: Record<string, any> }) => ChannelAgentTool[];

// Alias used by channel.ts directory adapter.
export type DirectoryPeer = import("openclaw/plugin-sdk").ChannelDirectoryEntry;

// ---------------------------------------------------------------------------
// Garmin-specific types (plugin's own data models)
// ---------------------------------------------------------------------------

export interface ResolvedGarminAccount {
  accountId: string;
  enabled: boolean;
  config: {
    binaryPath?: string;
    sessionDir?: string;
    verbose?: boolean;
    dmPolicy?: "open" | "pairing" | "allowlist";
    allowFrom?: string[];
  };
}

export interface OtpRequestResult {
  ok: boolean;
  requestId?: string;
  validUntil?: string;
  attemptsRemaining?: number;
  error?: string;
}

export interface OtpConfirmResult {
  ok: boolean;
  instanceId?: string;
  fcmStatus?: string;
  error?: string;
}

// ---------------------------------------------------------------------------
// MCP resource shapes (matching Go MCP server JSON output)
// ---------------------------------------------------------------------------

export interface GarminStatus {
  logged_in: boolean;
  listening: boolean;
  instance_id?: string;
}

export interface GarminContacts {
  members: Record<string, GarminMember>;
  conversations: GarminConversation[];
  addresses: Record<string, string>;
}

export interface GarminMember {
  userId: string;
  displayName?: string;
}

export interface GarminConversation {
  conversationId: string;
  displayName?: string;
}

export interface GarminUserLocation {
  latitudeDegrees?: number;
  longitudeDegrees?: number;
  elevationMeters?: number;
  groundVelocityMetersPerSecond?: number;
  courseDegrees?: number;
}

export interface GarminMediaMetadata {
  width?: number;
  height?: number;
  durationMs?: number;
}

export interface GarminMessage {
  messageId: string;
  conversationId?: string;
  parentMessageId?: string;
  messageBody?: string;
  to?: string[];
  from?: string;
  sentAt?: string;
  receivedAt?: string;
  messageType?: string;
  userLocation?: GarminUserLocation;
  referencePoint?: GarminUserLocation;
  mapShareUrl?: string;
  mapSharePassword?: string;
  liveTrackUrl?: string;
  fromDeviceType?: string;
  mediaId?: string;
  mediaType?: string;
  mediaMetadata?: GarminMediaMetadata;
  uuid?: string;
  transcription?: string;
  otaUuid?: string;
  fromUnitId?: string;
  intendedUnitId?: string;
}

export interface GarminConversationDetail {
  metaData: { conversationId?: string; [key: string]: unknown };
  messages: GarminMessage[];
  limit?: number;
  lastMessageId?: string;
}
