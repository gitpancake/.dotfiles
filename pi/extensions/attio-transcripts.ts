import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

type AttioTranscriptInput = {
  transcriptUrl?: string;
  meetingId?: string;
  callRecordingId?: string;
  maxChars?: number;
};

type ParsedTranscriptRef = {
  meetingId: string;
  callRecordingId: string;
};

const defaultAttioApiBaseUrl = "https://api.attio.com";
const defaultMaxChars = 20_000;
const maximumMaxChars = 100_000;

loadKnownEnvFiles();

export default function attioTranscripts(pi: ExtensionAPI) {
  pi.registerTool({
    name: "attio_call_transcript_get",
    label: "Attio Transcript",
    description:
      "Fetch a read-only Attio call recording transcript from an Attio transcript URL or explicit meeting/call recording IDs.",
    promptSnippet:
      "Read Attio call recording transcripts using ATTIO_API_KEY/PI_ATTIO_API_KEY from ~/.pi/agent/.env.",
    promptGuidelines: [
      "Use attio_call_transcript_get when the user provides an Attio transcript/call URL or explicit Attio meeting and call recording IDs.",
      "Never print Attio API keys; attio_call_transcript_get reads credentials from ~/.pi/agent/.env and does not expose them.",
      "Treat Attio transcript contents as private customer/account context; quote only what is necessary for the user's request.",
    ],
    parameters: Type.Object({
      transcriptUrl: Type.Optional(
        Type.String({
          description:
            "Attio web-app transcript URL, e.g. https://app.attio.com/<workspace>/calls/<meeting_id>/<call_recording_id>/transcript.",
        }),
      ),
      meetingId: Type.Optional(
        Type.String({ description: "Attio meeting ID. Optional when transcriptUrl is supplied." }),
      ),
      callRecordingId: Type.Optional(
        Type.String({ description: "Attio call recording ID. Optional when transcriptUrl is supplied." }),
      ),
      maxChars: Type.Optional(
        Type.Number({
          description: `Maximum transcript/result characters to return, 1-${maximumMaxChars}. Defaults to ${defaultMaxChars}.`,
        }),
      ),
    }),
    async execute(_toolCallId, params: AttioTranscriptInput, signal) {
      try {
        const transcriptRef = parseTranscriptInput(params);
        if (!transcriptRef) {
          return errorResult(
            "INVALID_INPUT",
            "attio_call_transcript_get requires transcriptUrl or both meetingId and callRecordingId.",
          );
        }

        const apiKey = getAttioApiKey();
        if (!apiKey) {
          return errorResult(
            "TOOL_NOT_CONFIGURED",
            "Set PI_ATTIO_API_KEY or ATTIO_API_KEY in ~/.pi/agent/.env, then run /reload.",
          );
        }

        const apiBaseUrl = (process.env.ATTIO_API_BASE_URL ?? defaultAttioApiBaseUrl).replace(/\/+$/, "");
        const url = `${apiBaseUrl}/v2/meetings/${encodeURIComponent(transcriptRef.meetingId)}/call_recordings/${encodeURIComponent(transcriptRef.callRecordingId)}/transcript`;
        const response = await fetch(url, {
          method: "GET",
          headers: {
            authorization: `Bearer ${apiKey}`,
            accept: "application/json",
          },
          signal,
        });

        const body = await response.json().catch(() => null);
        if (!response.ok) {
          return errorResult(
            "ATTIO_HTTP_ERROR",
            `Attio API returned HTTP ${response.status}: ${attioErrorSummary(body)}`,
          );
        }

        const maxChars = clampMaxChars(params.maxChars);
        const serialized = JSON.stringify(body, null, 2) ?? "null";
        const text = truncate(serialized, maxChars);

        return {
          content: [
            {
              type: "text" as const,
              text: `Fetched Attio transcript ${transcriptRef.meetingId}/${transcriptRef.callRecordingId}.\n\n${text}`,
            },
          ],
          details: {
            meetingId: transcriptRef.meetingId,
            callRecordingId: transcriptRef.callRecordingId,
            truncated: serialized.length > text.length,
            returnedChars: text.length,
          },
        };
      } catch (error) {
        return errorResult("ATTIO_TOOL_ERROR", error instanceof Error ? error.message : String(error));
      }
    },
  });
}

function loadKnownEnvFiles() {
  const candidates = [
    process.env.PI_ATTIO_ENV_FILE,
    path.join(os.homedir(), ".pi/agent/.env.local"),
    path.join(os.homedir(), ".pi/agent/.env"),
    path.join(os.homedir(), ".pi/.env"),
    path.resolve(process.cwd(), ".env.local"),
    path.resolve(process.cwd(), ".env"),
  ].filter((candidate): candidate is string => Boolean(candidate));

  for (const filePath of candidates) {
    if (!fs.existsSync(filePath)) continue;
    const content = fs.readFileSync(filePath, "utf8");
    for (const line of content.split(/\r?\n/)) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith("#") || !trimmed.includes("=")) continue;
      const [rawKey, ...rawValueParts] = trimmed.split("=");
      const key = rawKey?.trim();
      if (!key || process.env[key]) continue;
      process.env[key] = parseEnvValue(rawValueParts.join("="));
    }
  }
}

function parseEnvValue(value: string): string {
  const trimmed = value.trim();
  if (
    (trimmed.startsWith('"') && trimmed.endsWith('"')) ||
    (trimmed.startsWith("'") && trimmed.endsWith("'"))
  ) {
    return trimmed.slice(1, -1);
  }
  return trimmed;
}

function getAttioApiKey(): string | undefined {
  return firstNonEmpty(
    process.env.PI_ATTIO_API_KEY,
    process.env.ATTIO_API_KEY,
    process.env.STAN_ATTIO_API_KEY,
  );
}

function firstNonEmpty(...values: Array<string | undefined>): string | undefined {
  return values.find((value) => value && value.trim().length > 0)?.trim();
}

function parseTranscriptInput(input: AttioTranscriptInput): ParsedTranscriptRef | undefined {
  const explicitMeetingId = input.meetingId?.trim();
  const explicitCallRecordingId = input.callRecordingId?.trim();
  if (explicitMeetingId && explicitCallRecordingId) {
    return { meetingId: explicitMeetingId, callRecordingId: explicitCallRecordingId };
  }

  const transcriptUrl = input.transcriptUrl?.trim();
  if (!transcriptUrl) return undefined;

  try {
    const url = new URL(transcriptUrl);
    const segments = url.pathname.split("/").filter(Boolean);
    const callsIndex = segments.indexOf("calls");
    const meetingId = callsIndex >= 0 ? segments[callsIndex + 1] : undefined;
    const callRecordingId = callsIndex >= 0 ? segments[callsIndex + 2] : undefined;
    if (meetingId && callRecordingId) return { meetingId, callRecordingId };
  } catch {
    return undefined;
  }

  return undefined;
}

function clampMaxChars(maxChars: number | undefined): number {
  if (!Number.isFinite(maxChars ?? defaultMaxChars)) return defaultMaxChars;
  return Math.min(Math.max(Math.trunc(maxChars ?? defaultMaxChars), 1), maximumMaxChars);
}

function truncate(text: string, maxChars: number): string {
  if (text.length <= maxChars) return text;
  return `${text.slice(0, maxChars)}\n\n[truncated ${text.length - maxChars} chars; rerun with a higher maxChars if needed]`;
}

function attioErrorSummary(body: unknown): string {
  if (!body || typeof body !== "object") return "no JSON error body";
  const record = body as { message?: unknown; error?: unknown; code?: unknown };
  if (typeof record.message === "string") return record.message;
  if (typeof record.error === "string") return record.error;
  if (typeof record.code === "string") return record.code;
  return "unrecognized JSON error body";
}

function errorResult(code: string, message: string) {
  return {
    isError: true,
    content: [{ type: "text" as const, text: `${code}: ${message}` }],
    details: { code, message },
  };
}
