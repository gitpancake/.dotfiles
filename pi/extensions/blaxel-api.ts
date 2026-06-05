import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { Type } from "@earendil-works/pi-ai";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

type BlaxelApiInput = {
  action:
    | "getSandbox"
    | "listSandboxes"
    | "summarizeSandboxes"
    | "deleteOldSandboxes"
    | "request";
  workspace?: string;
  sandboxName?: string;
  sandboxUrl?: string;
  path?: string;
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  query?: Record<string, string | number | boolean>;
  body?: unknown;
  limit?: number;
  olderThanHours?: number;
  dryRun?: boolean;
  confirmDelete?: boolean;
  maxDeletes?: number;
};

type SandboxSummary = {
  name?: string;
  workspace?: string;
  status?: unknown;
  state?: unknown;
  createdAt?: unknown;
  updatedAt?: unknown;
  lastUsedAt?: unknown;
  expiresIn?: unknown;
  runtimeTtl?: unknown;
  runtimeExpires?: unknown;
  lifecycleExpirationPolicies?: unknown;
};

type SandboxListSummary = {
  count: number;
  returned: number;
  truncated: boolean;
  sandboxes: SandboxSummary[];
};

type OldSandboxSummary = {
  workspace: string;
  olderThanHours: number;
  totalCount: number;
  oldCount: number;
  recentCount: number;
  missingCreatedAtCount: number;
  oldestCreatedAt?: string;
  oldSandboxes: Array<{ name: string; createdAt: string; ageHours: number }>;
  truncated: boolean;
};

type DeleteOldSandboxSummary = OldSandboxSummary & {
  dryRun: boolean;
  attemptedDeletes: number;
  deletedCount: number;
  failedDeletes: Array<{ name: string; status: number }>;
};

const defaultBaseUrl = "https://api.blaxel.ai/v0";
const envPaths = [
  join(process.env.HOME ?? "", ".pi/agent/.env.local"),
  join(process.env.HOME ?? "", ".pi/agent/.env"),
];

export default function blaxelApi(pi: ExtensionAPI) {
  pi.registerTool({
    name: "blaxel_api",
    label: "Blaxel API",
    description:
      "Fetch Blaxel control-plane resources, especially sandbox TTL/lifecycle details.",
    promptSnippet:
      "Fetch Blaxel sandbox/control-plane details with credentials from ~/.pi/agent/.env.",
    promptGuidelines: [
      "Use blaxel_api when investigating Blaxel sandboxes, TTL/lifecycle policies, or control-plane state.",
      "Never include Blaxel API keys in responses; blaxel_api reads credentials from ~/.pi/agent/.env and redacts sensitive fields.",
    ],
    parameters: Type.Object({
      action: Type.Union([
        Type.Literal("getSandbox"),
        Type.Literal("listSandboxes"),
        Type.Literal("summarizeSandboxes"),
        Type.Literal("deleteOldSandboxes"),
        Type.Literal("request"),
      ]),
      workspace: Type.Optional(
        Type.String({
          description:
            "Blaxel workspace name. Defaults to BL_WORKSPACE or parsed sandbox URL.",
        }),
      ),
      sandboxName: Type.Optional(
        Type.String({ description: "Sandbox name for getSandbox." }),
      ),
      sandboxUrl: Type.Optional(
        Type.String({
          description:
            "Blaxel console URL; workspace and sandbox name are parsed from it.",
        }),
      ),
      path: Type.Optional(
        Type.String({
          description:
            "Control-plane path for request action, e.g. /sandboxes/name.",
        }),
      ),
      method: Type.Optional(
        Type.Union([
          Type.Literal("GET"),
          Type.Literal("POST"),
          Type.Literal("PUT"),
          Type.Literal("PATCH"),
          Type.Literal("DELETE"),
        ]),
      ),
      query: Type.Optional(
        Type.Record(
          Type.String(),
          Type.Union([Type.String(), Type.Number(), Type.Boolean()]),
        ),
      ),
      body: Type.Optional(Type.Unknown()),
      limit: Type.Optional(
        Type.Number({
          description: "Optional limit for list/summarize output.",
        }),
      ),
      olderThanHours: Type.Optional(
        Type.Number({
          description:
            "Age threshold for summarizeSandboxes/deleteOldSandboxes. Defaults to 1 hour.",
        }),
      ),
      dryRun: Type.Optional(
        Type.Boolean({
          description:
            "For deleteOldSandboxes, default true. Set false with confirmDelete=true to delete.",
        }),
      ),
      confirmDelete: Type.Optional(
        Type.Boolean({
          description:
            "Required true with dryRun=false for deleteOldSandboxes.",
        }),
      ),
      maxDeletes: Type.Optional(
        Type.Number({
          description: "Safety cap for deleteOldSandboxes. Defaults to 25.",
        }),
      ),
    }),
    async execute(_toolCallId, params: BlaxelApiInput, signal) {
      const parsedUrl = params.sandboxUrl
        ? parseSandboxUrl(params.sandboxUrl)
        : {};
      const workspace =
        params.workspace ??
        parsedUrl.workspace ??
        readEnvValue("BL_WORKSPACE") ??
        readEnvValue("BLAXEL_WORKSPACE");
      const apiKey =
        readEnvValue("BL_API_KEY") ?? readEnvValue("BLAXEL_API_KEY");

      if (!apiKey) {
        return errorResult(
          "Missing BL_API_KEY/BLAXEL_API_KEY in ~/.pi/agent/.env or process env.",
        );
      }
      if (!workspace) {
        return errorResult(
          "Missing workspace. Pass workspace, sandboxUrl, or set BL_WORKSPACE in ~/.pi/agent/.env.",
        );
      }

      const request = buildRequest(params, parsedUrl);
      if ("error" in request) return errorResult(request.error);

      const response = await fetchBlaxel({
        apiKey,
        workspace,
        method: request.method,
        path: request.path,
        query: request.query,
        body: request.body,
        signal,
      });

      const sanitized = redactSensitive(response.data);
      if (
        response.ok &&
        (params.action === "summarizeSandboxes" ||
          params.action === "deleteOldSandboxes")
      ) {
        const oldSummary = summarizeOldSandboxes({
          data: sanitized,
          workspace,
          olderThanHours: params.olderThanHours ?? 1,
          outputLimit: params.limit ?? 25,
        });

        if (!oldSummary) {
          return errorResult("Could not parse Blaxel sandboxes response.");
        }

        if (params.action === "summarizeSandboxes") {
          return compactResult({
            text: formatOldSandboxSummary(oldSummary),
            details: { ok: true, status: response.status, summary: oldSummary },
          });
        }

        const deleteSummary = await deleteOldSandboxes({
          apiKey,
          workspace,
          oldSummary,
          dryRun: params.dryRun ?? true,
          confirmDelete: params.confirmDelete === true,
          maxDeletes: params.maxDeletes ?? 25,
          signal,
        });

        return compactResult({
          text: formatDeleteOldSandboxSummary(deleteSummary),
          details: {
            ok: true,
            status: response.status,
            summary: deleteSummary,
          },
        });
      }

      const sandboxSummary =
        params.action === "getSandbox" && response.ok
          ? summarizeSandbox(sanitized)
          : undefined;
      const sandboxListSummary =
        params.action === "listSandboxes" && response.ok
          ? summarizeSandboxList(sanitized, params.limit ?? 25)
          : undefined;
      const text = formatToolResult({
        action: params.action,
        ok: response.ok,
        status: response.status,
        sandboxSummary,
        sandboxListSummary,
        data: sanitized,
      });

      return {
        content: [{ type: "text", text }],
        details: {
          ok: response.ok,
          status: response.status,
          summary: sandboxSummary ?? sandboxListSummary,
          data: sanitized,
        },
        isError: !response.ok,
      };
    },
  });
}

function buildRequest(
  params: BlaxelApiInput,
  parsedUrl: Partial<{ sandboxName: string }>,
) {
  if (params.action === "getSandbox") {
    const sandboxName = params.sandboxName ?? parsedUrl.sandboxName;
    if (!sandboxName)
      return {
        error: "getSandbox requires sandboxName or sandboxUrl.",
      } as const;
    return {
      method: "GET" as const,
      path: `/sandboxes/${encodeURIComponent(sandboxName)}`,
      query: params.query,
      body: undefined,
    };
  }

  if (
    params.action === "listSandboxes" ||
    params.action === "summarizeSandboxes" ||
    params.action === "deleteOldSandboxes"
  ) {
    return {
      method: "GET" as const,
      path: "/sandboxes",
      query: {
        ...(params.query ?? {}),
        ...(params.limit ? { limit: params.limit } : {}),
      },
      body: undefined,
    };
  }

  if (!params.path) return { error: "request action requires path." } as const;
  return {
    method: params.method ?? "GET",
    path: params.path.startsWith("/") ? params.path : `/${params.path}`,
    query: params.query,
    body: params.body,
  };
}

async function fetchBlaxel(input: {
  apiKey: string;
  workspace: string;
  method: string;
  path: string;
  query?: Record<string, string | number | boolean>;
  body?: unknown;
  signal?: AbortSignal;
}) {
  const url = new URL(`${defaultBaseUrl}${input.path}`);
  for (const [key, value] of Object.entries(input.query ?? {}))
    url.searchParams.set(key, String(value));

  const response = await fetch(url, {
    method: input.method,
    headers: {
      Accept: "application/json",
      Authorization: `Bearer ${input.apiKey}`,
      "Content-Type": "application/json",
      "X-Blaxel-Workspace": input.workspace,
    },
    body: input.body === undefined ? undefined : JSON.stringify(input.body),
    signal: input.signal,
  });

  const text = await response.text();
  const data = parseJsonOrText(text);
  return { ok: response.ok, status: response.status, data };
}

function parseSandboxUrl(value: string) {
  try {
    const url = new URL(value);
    const segments = url.pathname.split("/").filter(Boolean);
    const workspacesIndex = segments.indexOf("workspaces");
    const workspace =
      workspacesIndex >= 0 ? segments[workspacesIndex + 1] : segments[0];
    const sandboxIndex = firstIndexOf(segments, ["sandbox", "sandboxes"]);
    return {
      workspace,
      sandboxName: sandboxIndex >= 0 ? segments[sandboxIndex + 1] : undefined,
    };
  } catch {
    return {};
  }
}

function readEnvValue(key: string) {
  if (process.env[key]) return process.env[key];

  for (const path of envPaths) {
    if (!existsSync(path)) continue;
    const lines = readFileSync(path, "utf8").split(/\r?\n/);
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith("#")) continue;
      const separator = trimmed.indexOf("=");
      if (separator < 0) continue;
      if (trimmed.slice(0, separator).trim() !== key) continue;
      return unquoteEnvValue(trimmed.slice(separator + 1).trim());
    }
  }

  return undefined;
}

function unquoteEnvValue(value: string) {
  if (
    (value.startsWith('"') && value.endsWith('"')) ||
    (value.startsWith("'") && value.endsWith("'"))
  ) {
    return value.slice(1, -1);
  }
  return value;
}

function parseJsonOrText(text: string) {
  if (!text) return undefined;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return text;
  }
}

function summarizeSandbox(data: unknown): SandboxSummary | undefined {
  if (!isRecord(data)) return undefined;
  const metadata = recordValue(data, "metadata");
  const spec = recordValue(data, "spec");
  const runtime = recordValue(spec, "runtime");
  const lifecycle = recordValue(spec, "lifecycle");

  return {
    name: stringValue(metadata, "name") ?? stringValue(data, "name"),
    workspace:
      stringValue(metadata, "workspace") ?? stringValue(data, "workspace"),
    status: data.status,
    state: data.state,
    createdAt: metadata?.createdAt ?? data.createdAt ?? null,
    updatedAt: metadata?.updatedAt ?? data.updatedAt ?? null,
    lastUsedAt: data.lastUsedAt ?? null,
    expiresIn: data.expiresIn ?? null,
    runtimeTtl: runtime?.ttl ?? null,
    runtimeExpires: runtime?.expires ?? null,
    lifecycleExpirationPolicies:
      lifecycle?.expirationPolicies ?? lifecycle?.expiration_policies ?? null,
  };
}

function summarizeSandboxList(
  data: unknown,
  outputLimit: number,
): SandboxListSummary | undefined {
  const sandboxes = extractSandboxItems(data);
  if (!sandboxes) return undefined;

  const summaries = sandboxes
    .slice(0, outputLimit)
    .map((sandbox) => summarizeSandbox(sandbox))
    .filter((sandbox): sandbox is SandboxSummary => sandbox !== undefined);

  return {
    count: sandboxes.length,
    returned: summaries.length,
    truncated: sandboxes.length > summaries.length,
    sandboxes: summaries,
  };
}

function summarizeOldSandboxes(input: {
  data: unknown;
  workspace: string;
  olderThanHours: number;
  outputLimit: number;
}): OldSandboxSummary | undefined {
  const sandboxes = extractSandboxItems(input.data);
  if (!sandboxes) return undefined;

  const cutoffMs = Date.now() - input.olderThanHours * 60 * 60 * 1000;
  const oldSandboxes: Array<{
    name: string;
    createdAt: string;
    ageHours: number;
  }> = [];
  let recentCount = 0;
  let missingCreatedAtCount = 0;
  let oldestCreatedAt: string | undefined;

  for (const sandbox of sandboxes) {
    const name = sandboxName(sandbox);
    const createdAt = sandboxCreatedAt(sandbox);
    if (!name || !createdAt) {
      missingCreatedAtCount += 1;
      continue;
    }

    const createdMs = Date.parse(createdAt);
    if (Number.isNaN(createdMs)) {
      missingCreatedAtCount += 1;
      continue;
    }

    if (!oldestCreatedAt || createdMs < Date.parse(oldestCreatedAt)) {
      oldestCreatedAt = createdAt;
    }

    if (createdMs <= cutoffMs) {
      oldSandboxes.push({
        name,
        createdAt,
        ageHours: roundHours((Date.now() - createdMs) / (60 * 60 * 1000)),
      });
    } else {
      recentCount += 1;
    }
  }

  oldSandboxes.sort(
    (left, right) => Date.parse(left.createdAt) - Date.parse(right.createdAt),
  );

  return {
    workspace: input.workspace,
    olderThanHours: input.olderThanHours,
    totalCount: sandboxes.length,
    oldCount: oldSandboxes.length,
    recentCount,
    missingCreatedAtCount,
    oldestCreatedAt,
    oldSandboxes: oldSandboxes.slice(0, input.outputLimit),
    truncated: oldSandboxes.length > input.outputLimit,
  };
}

async function deleteOldSandboxes(input: {
  apiKey: string;
  workspace: string;
  oldSummary: OldSandboxSummary;
  dryRun: boolean;
  confirmDelete: boolean;
  maxDeletes: number;
  signal?: AbortSignal;
}): Promise<DeleteOldSandboxSummary> {
  if (input.dryRun || !input.confirmDelete) {
    return {
      ...input.oldSummary,
      dryRun: true,
      attemptedDeletes: 0,
      deletedCount: 0,
      failedDeletes: [],
    };
  }

  const targets = input.oldSummary.oldSandboxes.slice(0, input.maxDeletes);
  const failedDeletes: Array<{ name: string; status: number }> = [];
  let deletedCount = 0;

  for (const sandbox of targets) {
    const response = await fetchBlaxel({
      apiKey: input.apiKey,
      workspace: input.workspace,
      method: "DELETE",
      path: `/sandboxes/${encodeURIComponent(sandbox.name)}`,
      signal: input.signal,
    });

    if (response.ok) {
      deletedCount += 1;
    } else {
      failedDeletes.push({ name: sandbox.name, status: response.status });
    }
  }

  return {
    ...input.oldSummary,
    dryRun: false,
    attemptedDeletes: targets.length,
    deletedCount,
    failedDeletes,
  };
}

function formatOldSandboxSummary(summary: OldSandboxSummary) {
  return [
    `Blaxel sandboxes in ${summary.workspace}: ${summary.totalCount} total`,
    `${summary.oldCount} older than ${summary.olderThanHours} hour(s); ${summary.recentCount} newer; ${summary.missingCreatedAtCount} missing/invalid createdAt.`,
    summary.oldestCreatedAt
      ? `Oldest createdAt: ${summary.oldestCreatedAt}`
      : undefined,
    summary.oldSandboxes.length > 0
      ? `Old sandboxes${summary.truncated ? " (truncated)" : ""}:\n${JSON.stringify(summary.oldSandboxes, null, 2)}`
      : "No old sandboxes matched.",
  ]
    .filter((line): line is string => Boolean(line))
    .join("\n");
}

function formatDeleteOldSandboxSummary(summary: DeleteOldSandboxSummary) {
  const mode = summary.dryRun
    ? "dry run; no sandboxes deleted"
    : `${summary.deletedCount}/${summary.attemptedDeletes} sandboxes deleted`;

  return [
    `Blaxel old sandbox cleanup for ${summary.workspace}: ${mode}`,
    `${summary.oldCount} matched older than ${summary.olderThanHours} hour(s).`,
    summary.dryRun
      ? "Pass dryRun=false and confirmDelete=true to delete matched sandboxes."
      : undefined,
    summary.failedDeletes.length > 0
      ? `Failed deletes: ${JSON.stringify(summary.failedDeletes, null, 2)}`
      : undefined,
  ]
    .filter((line): line is string => Boolean(line))
    .join("\n");
}

function compactResult(input: { text: string; details: unknown }) {
  return {
    content: [{ type: "text" as const, text: input.text }],
    details: input.details,
  };
}

function sandboxName(value: unknown) {
  if (!isRecord(value)) return undefined;
  const metadata = recordValue(value, "metadata");
  return stringValue(metadata, "name") ?? stringValue(value, "name");
}

function sandboxCreatedAt(value: unknown) {
  if (!isRecord(value)) return undefined;
  const metadata = recordValue(value, "metadata");
  const createdAt = metadata?.createdAt ?? value.createdAt;
  return typeof createdAt === "string" ? createdAt : undefined;
}

function roundHours(value: number) {
  return Math.round(value * 10) / 10;
}

function formatToolResult(input: {
  action: string;
  ok: boolean;
  status: number;
  sandboxSummary?: SandboxSummary;
  sandboxListSummary?: SandboxListSummary;
  data: unknown;
}) {
  const lines = [
    `Blaxel ${input.action}: HTTP ${input.status}${input.ok ? "" : " (failed)"}`,
  ];
  if (input.sandboxSummary) {
    lines.push(
      "",
      "Sandbox summary:",
      JSON.stringify(input.sandboxSummary, null, 2),
    );
  } else if (input.sandboxListSummary) {
    lines.push(
      "",
      "Sandbox list summary:",
      JSON.stringify(input.sandboxListSummary, null, 2),
    );
  } else {
    lines.push("", "Response:", JSON.stringify(input.data, null, 2));
  }
  return lines.join("\n");
}

function errorResult(message: string) {
  return {
    content: [{ type: "text" as const, text: message }],
    details: { message },
    isError: true,
  };
}

function redactSensitive(value: unknown): unknown {
  if (Array.isArray(value)) return value.map((item) => redactSensitive(item));
  if (!isRecord(value)) return value;

  const result: Record<string, unknown> = {};
  const isSecretEnv = value.secret === true;
  for (const [key, child] of Object.entries(value)) {
    const lowerKey = key.toLowerCase();
    if (
      lowerKey.includes("authorization") ||
      lowerKey.includes("apikey") ||
      lowerKey.includes("api_key") ||
      lowerKey.includes("token") ||
      lowerKey.includes("secret")
    ) {
      result[key] = "[REDACTED]";
    } else if (isSecretEnv && key === "value") {
      result[key] = "[REDACTED]";
    } else {
      result[key] = redactSensitive(child);
    }
  }
  return result;
}

function extractSandboxItems(data: unknown) {
  if (Array.isArray(data)) return data;
  if (!isRecord(data)) return undefined;

  const candidates = [data.sandboxes, data.items, data.results, data.data];
  for (const candidate of candidates) {
    if (Array.isArray(candidate)) return candidate;
  }

  return undefined;
}

function firstIndexOf(values: string[], candidates: string[]) {
  for (const candidate of candidates) {
    const index = values.indexOf(candidate);
    if (index >= 0) return index;
  }
  return -1;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function recordValue(value: unknown, key: string) {
  if (!isRecord(value)) return undefined;
  const child = value[key];
  return isRecord(child) ? child : undefined;
}

function stringValue(value: unknown, key: string) {
  if (!isRecord(value)) return undefined;
  const child = value[key];
  return typeof child === "string" ? child : undefined;
}
