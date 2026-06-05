import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

type JsonValue =
  | null
  | boolean
  | number
  | string
  | JsonValue[]
  | { [key: string]: JsonValue };
type JsonObject = { [key: string]: JsonValue };

loadKnownEnvFiles();
applyEnvAliases();

const AXIOM_API_BASE = process.env.AXIOM_API_BASE ?? "https://api.axiom.co";
const LANGSMITH_API_BASE =
  process.env.LANGSMITH_ENDPOINT ?? "https://api.smith.langchain.com";
const SENTRY_API_BASE = process.env.SENTRY_API_BASE ?? "https://sentry.io";

function loadKnownEnvFiles() {
  const candidates = [
    process.env.PI_OBSERVABILITY_ENV_FILE,
    path.join(os.homedir(), ".pi/agent/.env.local"),
    path.join(os.homedir(), ".pi/agent/.env"),
    path.join(os.homedir(), ".pi/.env"),
    path.resolve(process.cwd(), ".env.local"),
    path.resolve(process.cwd(), ".env"),
    path.resolve(process.cwd(), "../cartage-agent/.env.local"),
    path.resolve(process.cwd(), "../cartage-agent/.env"),
    path.resolve(process.cwd(), "cartage-agent/.env.local"),
    path.resolve(process.cwd(), "cartage-agent/.env"),
    path.join(os.homedir(), "Documents/code/cartage-agent/.env.local"),
    path.join(os.homedir(), "Documents/code/cartage-agent/.env"),
  ].filter((candidate): candidate is string => Boolean(candidate));

  for (const filePath of candidates) {
    if (!fs.existsSync(filePath)) continue;
    const content = fs.readFileSync(filePath, "utf8");
    for (const line of content.split(/\r?\n/)) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith("#") || !trimmed.includes("="))
        continue;
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

function applyEnvAliases() {
  process.env.AXIOM_API_TOKEN ??= process.env.AXIOM_TOKEN;
  process.env.SENTRY_AUTH_TOKEN ??=
    process.env.SENTRY_API_TOKEN ?? process.env.SENTRY_TOKEN;
}

function requiredEnv(name: string): string {
  const value = process.env[name];
  if (!value || value.trim().length === 0) {
    throw new Error(
      `Missing ${name}. Set it in your shell, Pi environment, or PI_OBSERVABILITY_ENV_FILE before using this tool.`,
    );
  }
  return value;
}

function optionalString(value: unknown): string | undefined {
  if (typeof value !== "string") return undefined;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : undefined;
}

function appendQuery(url: URL, params: Record<string, unknown>) {
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    url.searchParams.set(key, String(value));
  }
}

async function readJsonResponse(response: Response): Promise<JsonValue> {
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text) as JsonValue;
  } catch {
    return text;
  }
}

async function requestJson(
  input: RequestInfo | URL,
  init: RequestInit,
): Promise<JsonValue> {
  const response = await fetch(input, init);
  const body = await readJsonResponse(response);
  if (!response.ok) {
    const detail = typeof body === "string" ? body : JSON.stringify(body);
    throw new Error(
      `HTTP ${response.status} ${response.statusText}: ${detail}`,
    );
  }
  return body;
}

function axiomHeaders(): HeadersInit {
  const headers: Record<string, string> = {
    authorization: `Bearer ${requiredEnv("AXIOM_API_TOKEN")}`,
    "content-type": "application/json",
  };
  const orgId =
    optionalString(process.env.AXIOM_ORG_ID ?? process.env.AXIOM_PROJECT_ID) ??
    "cartage-q438";
  if (orgId) headers["x-axiom-org-id"] = orgId;
  return headers;
}

function langsmithHeaders(): HeadersInit {
  const headers: Record<string, string> = {
    "x-api-key": requiredEnv("LANGSMITH_API_KEY"),
    "content-type": "application/json",
  };
  const workspaceId = optionalString(process.env.LANGSMITH_WORKSPACE_ID);
  if (workspaceId) headers["x-tenant-id"] = workspaceId;
  return headers;
}

function sentryHeaders(): HeadersInit {
  return {
    authorization: `Bearer ${requiredEnv("SENTRY_AUTH_TOKEN")}`,
    "content-type": "application/json",
  };
}

function asObject(value: JsonValue): JsonObject {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value
    : {};
}

function truncateText(value: unknown, maxChars: number): string | undefined {
  if (typeof value !== "string") return undefined;
  return value.length > maxChars
    ? `${value.slice(0, maxChars)}… [truncated ${value.length - maxChars} chars]`
    : value;
}

const NOISY_OBSERVABILITY_KEYS = new Set([
  "executionSummary",
  "thread_history",
  "threadHistory",
  "channel_history",
  "channelHistory",
  "toolCalls",
  "accessToken",
]);

const SUMMARIZED_TEXT_KEYS = new Set([
  "markdownContent",
  "currentData",
  "previousData",
  "userRequest",
  "request",
]);

function redactSecretText(value: string): string {
  return value
    .replace(/xox[baprs]-[A-Za-z0-9-]+/g, "[redacted-slack-token]")
    .replace(/Bearer\s+[A-Za-z0-9._~+/-]+/gi, "Bearer [redacted]")
    .replace(/([A-Z0-9._%+-]+)@([A-Z0-9.-]+\.[A-Z]{2,})/gi, "$1@email.com");
}

function summarizeLargeText(value: string, maxChars: number): JsonValue {
  const redacted = redactSecretText(value);
  if (redacted.length <= maxChars) return redacted;
  return {
    preview: redacted.slice(0, Math.max(80, maxChars)),
    omittedChars: redacted.length - Math.max(80, maxChars),
  };
}

function sanitizeObservabilityValue(
  value: unknown,
  maxChars: number,
  key?: string,
  depth = 0,
): JsonValue {
  if (key && NOISY_OBSERVABILITY_KEYS.has(key)) {
    const text = typeof value === "string" ? value : JSON.stringify(value);
    return {
      omitted: true,
      reason: `noisy field ${key}`,
      chars: text?.length ?? null,
    };
  }

  if (typeof value === "string") {
    if (key && SUMMARIZED_TEXT_KEYS.has(key))
      return summarizeLargeText(value, maxChars);
    return (
      truncateText(redactSecretText(value), maxChars) ?? redactSecretText(value)
    );
  }
  if (
    value === null ||
    typeof value === "boolean" ||
    typeof value === "number"
  ) {
    return value as JsonValue;
  }
  if (value === undefined) return null;
  if (depth >= 5) return summarizeLargeText(JSON.stringify(value), maxChars);

  if (Array.isArray(value)) {
    const limit = Math.min(value.length, 12);
    const items = value
      .slice(0, limit)
      .map((item) =>
        sanitizeObservabilityValue(item, maxChars, undefined, depth + 1),
      );
    if (value.length > limit) {
      items.push({ omittedItems: value.length - limit });
    }
    return items;
  }

  if (typeof value === "object") {
    const result: JsonObject = {};
    for (const [nestedKey, nestedValue] of Object.entries(value)) {
      const lowerKey = nestedKey.toLowerCase();
      if (
        lowerKey.includes("authorization") ||
        lowerKey.includes("cookie") ||
        lowerKey.includes("token") ||
        lowerKey.includes("secret") ||
        lowerKey.includes("apikey") ||
        lowerKey.includes("api_key")
      ) {
        result[nestedKey] = "[redacted]";
        continue;
      }
      result[nestedKey] = sanitizeObservabilityValue(
        nestedValue,
        maxChars,
        nestedKey,
        depth + 1,
      );
    }
    return result;
  }

  return summarizeLargeText(String(value), maxChars);
}

function previewValue(value: unknown, maxChars: number): JsonValue {
  return sanitizeObservabilityValue(value, maxChars);
}

function compactLangsmithRun(
  run: JsonValue,
  opts: { maxChars: number; view: "summary" | "io" | "messages" | "full" },
): JsonValue {
  if (opts.view === "full") {
    return {
      warning:
        "Full LangSmith runs are intentionally capped to protect Pi session context. Set PI_OBSERVABILITY_UNCAPPED_LANGSMITH_FULL=1 only for one-off raw debugging.",
      run:
        process.env.PI_OBSERVABILITY_UNCAPPED_LANGSMITH_FULL === "1"
          ? run
          : previewValue(run, opts.maxChars),
    };
  }
  const obj = asObject(run);
  const outputs = asObject(obj.outputs);
  const inputs = asObject(obj.inputs);
  const messages = Array.isArray(outputs.messages) ? outputs.messages : [];
  const base: JsonObject = {
    id: obj.id ?? null,
    traceId: obj.trace_id ?? null,
    name: obj.name ?? null,
    runType: obj.run_type ?? null,
    status: obj.status ?? null,
    error: obj.error ?? null,
    startTime: obj.start_time ?? null,
    endTime: obj.end_time ?? null,
    totalTokens: obj.total_tokens ?? null,
    totalCost: obj.total_cost ?? null,
    projectId: obj.session_id ?? obj.project_id ?? null,
    metadata: asObject(obj.extra).metadata ?? null,
    appPath: obj.app_path ?? null,
    childRunCount: Array.isArray(obj.child_run_ids)
      ? obj.child_run_ids.length
      : 0,
    directChildRunCount: Array.isArray(obj.direct_child_run_ids)
      ? obj.direct_child_run_ids.length
      : 0,
    inputsPreview: obj.inputs_preview ?? previewValue(inputs, opts.maxChars),
    outputsPreview: obj.outputs_preview ?? null,
  };

  if (opts.view === "io") {
    base.inputs = previewValue(inputs, opts.maxChars);
    base.outputs = previewValue(outputs, opts.maxChars);
  }

  if (opts.view === "messages") {
    const messageLimit = 20;
    base.messages = messages.slice(0, messageLimit).map((message, index) => {
      const messageObj = asObject(message as JsonValue);
      const kwargs = asObject(messageObj.kwargs);
      return {
        index,
        type: Array.isArray(messageObj.id)
          ? (messageObj.id.at(-1) ?? messageObj.type ?? null)
          : (messageObj.type ?? null),
        content: previewValue(kwargs.content, opts.maxChars),
        toolCalls: previewValue(kwargs.tool_calls, opts.maxChars),
        toolCallId: kwargs.tool_call_id ?? null,
      };
    });
    base.omittedMessages = Math.max(0, messages.length - messageLimit);
  }

  return base;
}

function compactLangsmithRuns(value: JsonValue, maxChars: number): JsonValue {
  const runs = Array.isArray(value)
    ? value
    : Array.isArray(asObject(value).runs)
      ? (asObject(value).runs as JsonValue[])
      : null;
  if (!runs) return previewValue(value, maxChars);
  return runs.map((run) =>
    compactLangsmithRun(run, { view: "summary", maxChars }),
  );
}

type AxiomView = "summary" | "raw";

type AxiomSummaryOptions = {
  view: AxiomView;
  maxRows: number;
  maxChars: number;
};

function compactAxiomResult(
  result: JsonValue,
  opts: AxiomSummaryOptions,
): JsonValue {
  if (opts.view === "raw") return capAxiomRaw(result, opts);

  const obj = asObject(result);
  const rows = extractAxiomRows(result);
  const rowSummaries = rows.map((row) => summarizeAxiomRow(row, opts.maxChars));
  const interesting = rowSummaries.filter(isInterestingAxiomRow);
  const timeline = rowSummaries.slice(0, opts.maxRows);

  return {
    format: obj.format ?? null,
    status: summarizeAxiomStatus(obj.status),
    rowsReturned: rows.length,
    rowsMatched: asObject(obj.status).rowsMatched ?? rows.length,
    groups: asObject(obj.status).numGroups ?? null,
    levels: countBy(rowSummaries, (row) => row.level ?? "unknown"),
    workflows: topCounts(rowSummaries, (row) => row.workflowName, 12),
    messages: topCounts(rowSummaries, (row) => row.message, 20),
    services: topCounts(rowSummaries, (row) => row.service, 12),
    warningsAndErrors: interesting.slice(0, opts.maxRows),
    timeline,
    omittedRows: Math.max(0, rows.length - timeline.length),
    buckets: previewValue(obj.buckets, opts.maxChars),
  };
}

function capAxiomRaw(result: JsonValue, opts: AxiomSummaryOptions): JsonValue {
  const obj = asObject(result);
  const rows = extractAxiomRows(result)
    .slice(0, opts.maxRows)
    .map((row) => previewValue(row, opts.maxChars));
  return {
    format: obj.format ?? null,
    status: summarizeAxiomStatus(obj.status),
    rowsReturned: extractAxiomRows(result).length,
    rows: rows as JsonValue[],
    omittedRows: Math.max(0, extractAxiomRows(result).length - rows.length),
    buckets: previewValue(obj.buckets, opts.maxChars),
  };
}

function summarizeAxiomStatus(status: unknown): JsonValue {
  const statusObj = asObject(status as JsonValue);
  if (Object.keys(statusObj).length === 0) return null;
  return {
    elapsedTime: statusObj.elapsedTime ?? null,
    rowsExamined: statusObj.rowsExamined ?? null,
    rowsMatched: statusObj.rowsMatched ?? null,
    blocksExamined: statusObj.blocksExamined ?? null,
    blocksMatched: statusObj.blocksMatched ?? null,
    blocksSkipped: statusObj.blocksSkipped ?? null,
    numGroups: statusObj.numGroups ?? null,
    isPartial: statusObj.isPartial ?? null,
    minBlockTime: statusObj.minBlockTime ?? null,
    maxBlockTime: statusObj.maxBlockTime ?? null,
  };
}

function extractAxiomRows(value: JsonValue): JsonObject[] {
  if (Array.isArray(value)) return value.filter(isJsonObject) as JsonObject[];
  const obj = asObject(value);
  if (Array.isArray(obj.matches))
    return obj.matches.filter(isJsonObject) as JsonObject[];
  if (Array.isArray(obj.rows))
    return obj.rows.filter(isJsonObject) as JsonObject[];

  const tables = Array.isArray(obj.tables) ? obj.tables : [];
  const firstTable = tables.find(isJsonObject) as JsonObject | undefined;
  if (firstTable) return extractAxiomTableRows(firstTable);

  return [];
}

function extractAxiomTableRows(table: JsonObject): JsonObject[] {
  const fields = Array.isArray(table.fields) ? table.fields : [];
  const columns = Array.isArray(table.columns) ? table.columns : [];
  const columnNames = fields.map((field, index) => {
    const name =
      isJsonObject(field) && typeof field.name === "string" ? field.name : null;
    return name ?? `col${index}`;
  });
  const rowCount = Array.isArray(columns[0]) ? columns[0].length : 0;
  const rows: JsonObject[] = [];
  for (let rowIndex = 0; rowIndex < rowCount; rowIndex += 1) {
    const row: JsonObject = {};
    for (
      let columnIndex = 0;
      columnIndex < columnNames.length;
      columnIndex += 1
    ) {
      const column = columns[columnIndex];
      row[columnNames[columnIndex]] = Array.isArray(column)
        ? (column[rowIndex] as JsonValue)
        : null;
    }
    rows.push(row);
  }
  return rows;
}

function summarizeAxiomRow(row: JsonObject, maxChars: number): JsonObject {
  const data = asObject(row.data);
  const log =
    data.message || data.level || data.workflowName || data.runId || data.orgId
      ? data
      : row;
  const nestedData = asObject(log.data);
  const attributes = asObject(data.attributes);
  const custom = asObject(attributes.custom);
  const resource = asObject(data.resource);
  const resourceCustom = asObject(resource.custom);
  const service = asObject(data.service);

  const extras: JsonObject = {};
  for (const [label, value] of Object.entries({
    tool: getFirst(log.tool, custom.tool),
    triggerRunId: getFirst(log.triggerRunId, custom["$metadata.ctx.run.id"]),
    metric: getFirst(nestedData.metric, custom.metric),
    operationName: getFirst(nestedData.operationName, custom.operationName),
    collectionName: getFirst(nestedData.collectionName, custom.collectionName),
    durationMs: getFirst(nestedData.durationMs, custom.durationMs),
    duration: getFirst(data.duration, log.duration),
    kind: data.kind,
    httpStatus: custom["http.status_code"],
    triggerTask: custom["$metadata.ctx.task.id"],
  })) {
    if (value !== undefined && value !== null && value !== "")
      extras[label] = previewValue(value, maxChars);
  }

  const rawError = getFirst(log.error, data.error, custom.error);
  return {
    time: getFirst(row._time, log._time),
    level: getFirst(log.level, log.severity, data.level),
    message: truncateText(
      String(getFirst(log.message, data.name, row.name, "(no message)")),
      maxChars,
    ),
    workflowName: getFirst(log.workflowName, custom.workflowName),
    requestId: getFirst(log.requestId, custom.requestId),
    runId: getFirst(log.runId, custom.runId),
    orgId: getFirst(log.orgId, custom.orgId),
    service: getFirst(
      service.name,
      resourceCustom["service.name"],
      data.service,
    ),
    traceId: getFirst(data.trace_id, custom.trace_id, log.traceId),
    spanId: getFirst(data.span_id, custom.span_id),
    error:
      rawError == null ? undefined : truncateText(String(rawError), maxChars),
    extras,
  };
}

function isInterestingAxiomRow(row: JsonObject): boolean {
  const level = typeof row.level === "string" ? row.level.toLowerCase() : "";
  const httpStatus = Number(asObject(row.extras).httpStatus);
  return (
    level === "error" ||
    level === "warn" ||
    level === "warning" ||
    Boolean(row.error) ||
    httpStatus >= 500
  );
}

function getFirst(...values: unknown[]): JsonValue | undefined {
  for (const value of values) {
    if (value !== undefined && value !== null && value !== "")
      return value as JsonValue;
  }
  return undefined;
}

function isJsonObject(value: unknown): value is JsonObject {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function countBy(
  rows: JsonObject[],
  getKey: (row: JsonObject) => unknown,
): JsonObject {
  const counts: Record<string, number> = {};
  for (const row of rows) {
    const key = String(getKey(row) ?? "unknown");
    counts[key] = (counts[key] ?? 0) + 1;
  }
  return counts;
}

function topCounts(
  rows: JsonObject[],
  getKey: (row: JsonObject) => unknown,
  limit: number,
): JsonObject[] {
  return Object.entries(
    countBy(
      rows.filter((row) => getKey(row) != null),
      getKey,
    ),
  )
    .sort((a, b) => b[1] - a[1])
    .slice(0, limit)
    .map(([value, count]) => ({ value, count }));
}

function aplString(value: string): string {
  return `'${value.replaceAll("'", "\\'")}'`;
}

function datasetApl(dataset: string): string {
  return `[${aplString(dataset)}]`;
}

function padIsoTime(value: unknown, padMs: number): string | undefined {
  if (typeof value !== "string") return undefined;
  const normalized = /(?:Z|[+-]\d\d:?\d\d)$/.test(value) ? value : `${value}Z`;
  const time = new Date(normalized).getTime();
  if (Number.isNaN(time)) return undefined;
  return new Date(time + padMs).toISOString();
}

async function fetchLangsmithRun(
  runId: string,
  signal?: AbortSignal,
): Promise<JsonValue> {
  const encodedRunId = encodeURIComponent(runId);
  return requestJson(new URL(`/runs/${encodedRunId}`, LANGSMITH_API_BASE), {
    method: "GET",
    headers: langsmithHeaders(),
    signal,
  });
}

const DEFAULT_LANGSMITH_PROJECT_NAMES = [
  "agent-production",
  "agents-production",
  "employees-production",
];

const DEFAULT_LANGSMITH_PROJECT_BY_CODING_PROJECT: Record<string, string[]> = {
  "cartage-agent": ["agent-production", "agents-production"],
  agents: ["employees-production"],
  "ai-employees": ["employees-production"],
  "cartage-ai-employees": ["employees-production"],
};

const DEFAULT_AXIOM_DATASET_BY_CODING_PROJECT: Record<string, string> = {
  "cartage-agent": "REDACTED-DATASET-NAME",
  agents: "cartage-ai-employees",
  "ai-employees": "cartage-ai-employees",
  "cartage-ai-employees": "cartage-ai-employees",
};

function isUuid(value: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
    value,
  );
}

function splitProjectNames(value: string | undefined): string[] {
  if (!value) return [];
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function parseLangsmithProjectMap(
  value: string | undefined,
): Record<string, string[]> {
  if (!value) return {};
  const entries: Record<string, string[]> = {};
  for (const entry of value.split(/[,;\n]/)) {
    const [rawCodingProject, rawProjects] = entry.split("=");
    const codingProject = rawCodingProject?.trim().toLowerCase();
    if (!codingProject || !rawProjects) continue;
    const projects = rawProjects
      .split(/[|+]/)
      .map((project) => project.trim())
      .filter(Boolean);
    if (projects.length > 0) entries[codingProject] = projects;
  }
  return entries;
}

function langsmithProjectMap(): Record<string, string[]> {
  return {
    ...DEFAULT_LANGSMITH_PROJECT_BY_CODING_PROJECT,
    ...parseLangsmithProjectMap(process.env.LANGSMITH_PROJECT_MAP),
  };
}

function parseAxiomDatasetMap(
  value: string | undefined,
): Record<string, string> {
  if (!value) return {};
  const entries: Record<string, string> = {};
  for (const entry of value.split(/[,;\n]/)) {
    const [rawCodingProject, rawDataset] = entry.split("=");
    const codingProject = rawCodingProject?.trim().toLowerCase();
    const dataset = rawDataset?.trim();
    if (codingProject && dataset) entries[codingProject] = dataset;
  }
  return entries;
}

function axiomDatasetMap(): Record<string, string> {
  return {
    ...DEFAULT_AXIOM_DATASET_BY_CODING_PROJECT,
    ...parseAxiomDatasetMap(process.env.AXIOM_DATASET_MAP),
  };
}

function knownCodingProjects(): Set<string> {
  return new Set([
    ...Object.keys(langsmithProjectMap()),
    ...Object.keys(axiomDatasetMap()),
  ]);
}

function detectCodingProject(cwd = process.cwd()): string | undefined {
  const projectNames = knownCodingProjects();
  const envProject = optionalString(
    process.env.PI_CODING_PROJECT,
  )?.toLowerCase();
  if (envProject && projectNames.has(envProject)) return envProject;

  let current = path.resolve(cwd);
  const home = path.resolve(os.homedir());
  while (true) {
    const name = path.basename(current).toLowerCase();
    if (projectNames.has(name)) return name;
    const parent = path.dirname(current);
    if (parent === current || current === home) return undefined;
    current = parent;
  }
}

function axiomDatasetName(explicitDataset: string | undefined): string {
  const explicit = optionalString(explicitDataset);
  if (explicit) return explicit;

  const codingProject = detectCodingProject();
  if (codingProject) {
    const dataset = axiomDatasetMap()[codingProject];
    if (dataset) return dataset;
  }

  return requiredEnv("AXIOM_DATASET");
}

function axiomDatasetDisplay(): string {
  try {
    return axiomDatasetName(undefined);
  } catch {
    return "missing AXIOM_DATASET";
  }
}

function langsmithProjectsForCodingProject(codingProject: string | undefined): {
  codingProject?: string;
  projectNames: string[];
} {
  const projectMap = langsmithProjectMap();
  const normalizedCodingProject = optionalString(codingProject)?.toLowerCase();
  if (normalizedCodingProject) {
    return {
      codingProject: normalizedCodingProject,
      projectNames:
        projectMap[normalizedCodingProject] ?? splitProjectNames(codingProject),
    };
  }

  const detectedCodingProject = detectCodingProject();
  return {
    codingProject: detectedCodingProject,
    projectNames: detectedCodingProject
      ? (projectMap[detectedCodingProject] ?? [])
      : [],
  };
}

function langsmithProjectCandidates(params: {
  projectName?: string;
  projectNames?: string[];
  codingProject?: string;
}): { names: string[]; isExplicit: boolean; codingProject?: string } {
  const explicitNames = uniqueStrings([
    ...splitProjectNames(params.projectName),
    ...(params.projectNames ?? []).flatMap((name) => splitProjectNames(name)),
  ]);
  if (explicitNames.length > 0)
    return { names: explicitNames, isExplicit: true };

  const mapped = langsmithProjectsForCodingProject(params.codingProject);
  if (mapped.projectNames.length > 0) {
    return {
      names: uniqueStrings(mapped.projectNames),
      isExplicit: Boolean(params.codingProject),
      codingProject: mapped.codingProject,
    };
  }

  return {
    names: uniqueStrings([
      ...splitProjectNames(process.env.LANGSMITH_PROJECTS),
      ...splitProjectNames(process.env.LANGSMITH_READ_PROJECT),
      ...splitProjectNames(process.env.LANGSMITH_PROJECT),
      ...DEFAULT_LANGSMITH_PROJECT_NAMES,
    ]),
    isExplicit: false,
    codingProject: mapped.codingProject,
  };
}

async function resolveLangsmithProjectId(
  projectNameOrId: string,
  signal?: AbortSignal,
): Promise<string | null> {
  if (isUuid(projectNameOrId)) return projectNameOrId;
  const url = new URL("/sessions", LANGSMITH_API_BASE);
  url.searchParams.set("name", projectNameOrId);
  const response = await requestJson(url, {
    method: "GET",
    headers: langsmithHeaders(),
    signal,
  });
  const sessions = Array.isArray(response) ? response : [response];
  const project = sessions.map(asObject).find((item) => item.id);
  return typeof project?.id === "string" ? project.id : null;
}

async function resolveLangsmithProjectIds(
  params: {
    projectName?: string;
    projectNames?: string[];
    codingProject?: string;
  },
  signal?: AbortSignal,
): Promise<{
  projectIds: string[];
  searchedProjects: string[];
  skippedProjects: string[];
  codingProject?: string;
}> {
  const candidates = langsmithProjectCandidates(params);
  const projectIds: string[] = [];
  const searchedProjects: string[] = [];
  const skippedProjects: string[] = [];

  for (const name of candidates.names) {
    const projectId = await resolveLangsmithProjectId(name, signal);
    if (projectId) {
      projectIds.push(projectId);
      searchedProjects.push(name);
      continue;
    }
    if (candidates.isExplicit)
      throw new Error(`LangSmith project not found: ${name}`);
    skippedProjects.push(name);
  }

  return {
    projectIds: uniqueStrings(projectIds),
    searchedProjects,
    skippedProjects,
    codingProject: candidates.codingProject,
  };
}

async function runAxiomApl(
  apl: string,
  options: { startTime?: string; endTime?: string; includeCursor?: boolean },
  signal?: AbortSignal,
): Promise<JsonValue> {
  const body: Record<string, unknown> = { apl, format: "legacy" };
  if (options.startTime) body.startTime = options.startTime;
  if (options.endTime) body.endTime = options.endTime;
  if (options.includeCursor !== undefined)
    body.includeCursor = options.includeCursor;

  const url = new URL("/v1/datasets/_apl", AXIOM_API_BASE);
  url.searchParams.set("format", "legacy");
  return requestJson(url, {
    method: "POST",
    headers: axiomHeaders(),
    body: JSON.stringify(body),
    signal,
  });
}

function containsDataClause(values: string[]): string {
  return values
    .filter((value) => value.trim().length > 0)
    .map((value) => `tostring(['data']) contains ${aplString(value)}`)
    .join(" or ");
}

function splitJsonPath(pathValue: string): string[] {
  return pathValue
    .replaceAll(/\[(?:'|")?([^'"\]]+)(?:'|")?\]/g, ".$1")
    .split(".")
    .map((part) => part.trim())
    .filter(Boolean);
}

function getPathValue(value: unknown, pathValue: string): unknown {
  let current: unknown = value;
  for (const part of splitJsonPath(pathValue)) {
    if (current == null) return undefined;
    if (Array.isArray(current)) {
      const index = Number(part);
      current = Number.isInteger(index) ? current[index] : undefined;
      continue;
    }
    if (typeof current !== "object") return undefined;
    current = (current as Record<string, unknown>)[part];
  }
  return current;
}

function projectAxiomRows(
  result: JsonValue,
  fields: string[],
  opts: { maxRows: number; maxChars: number },
): JsonValue {
  const rows = extractAxiomRows(result);
  const projected = rows.slice(0, opts.maxRows).map((row) => {
    const out: JsonObject = {};
    for (const field of fields) {
      out[field] = previewValue(getPathValue(row, field), opts.maxChars);
    }
    return out;
  });
  return {
    status: summarizeAxiomStatus(asObject(result).status),
    rowsReturned: rows.length,
    rows: projected,
    omittedRows: Math.max(0, rows.length - projected.length),
  };
}

type OutputMode = "compact" | "verbose";
type LangsmithAction = "getRun" | "listRuns";
type AxiomAction = "apl" | "datasetQuery";
type SentryAction =
  | "getIssue"
  | "listIssueEvents"
  | "getIssueEvent"
  | "debugIssue";

function outputMode(value: unknown): OutputMode {
  return value === "verbose" ? "verbose" : "compact";
}

function axiomViewForOutput(output: OutputMode): AxiomView {
  return output === "verbose" ? "raw" : "summary";
}

function defaultMaxRows(
  output: OutputMode,
  value: unknown,
  compactDefault: number,
  verboseDefault: number,
): number {
  const requested =
    typeof value === "number"
      ? value
      : output === "verbose"
        ? verboseDefault
        : compactDefault;
  return Math.min(Math.max(requested, 1), output === "verbose" ? 50 : 100);
}

function defaultMaxChars(
  output: OutputMode,
  value: unknown,
  compactDefault: number,
  verboseDefault: number,
): number {
  const requested =
    typeof value === "number"
      ? value
      : output === "verbose"
        ? verboseDefault
        : compactDefault;
  return Math.min(
    Math.max(requested, 80),
    output === "verbose" ? 8_000 : 2_000,
  );
}

async function executeAxiom(
  params: {
    action: AxiomAction;
    apl?: string;
    dataset?: string;
    query?: string;
    startTime?: string;
    endTime?: string;
    includeCursor?: boolean;
    limit?: number;
    output?: OutputMode;
    maxRows?: number;
    maxChars?: number;
    selectFields?: string[];
  },
  signal?: AbortSignal,
): Promise<JsonValue> {
  const output = outputMode(params.output);
  const view = axiomViewForOutput(output);
  const maxRows = defaultMaxRows(output, params.maxRows, 10, 25);
  const maxChars = defaultMaxChars(output, params.maxChars, 400, 2_000);

  if (params.action === "apl") {
    if (!params.apl) throw new Error('axiom action "apl" requires apl.');
    const result = await runAxiomApl(
      params.apl,
      {
        startTime: params.startTime,
        endTime: params.endTime,
        includeCursor: params.includeCursor,
      },
      signal,
    );
    if (params.selectFields?.length) {
      return projectAxiomRows(result, params.selectFields, {
        maxRows,
        maxChars,
      });
    }
    return compactAxiomResult(result, { view, maxRows, maxChars });
  }

  if (!params.query)
    throw new Error('axiom action "datasetQuery" requires query.');
  const body: Record<string, unknown> = {
    query: params.query,
    format: "legacy",
  };
  if (params.startTime) body.startTime = params.startTime;
  if (params.endTime) body.endTime = params.endTime;
  if (params.limit !== undefined) body.limit = params.limit;

  const datasetName = axiomDatasetName(params.dataset);
  const dataset = encodeURIComponent(datasetName);
  const result = await requestJson(
    new URL(`/v1/datasets/${dataset}/query`, AXIOM_API_BASE),
    {
      method: "POST",
      headers: axiomHeaders(),
      body: JSON.stringify(body),
      signal,
    },
  );
  if (params.selectFields?.length) {
    return projectAxiomRows(result, params.selectFields, { maxRows, maxChars });
  }
  return compactAxiomResult(result, { view, maxRows, maxChars });
}

async function langsmithQueryBody(
  params: {
    projectName?: string;
    projectNames?: string[];
    codingProject?: string;
    traceId?: string;
    runId?: string;
    runType?: string;
    startTime?: string;
    endTime?: string;
    error?: boolean;
    limit?: number;
  },
  signal?: AbortSignal,
): Promise<{
  body: Record<string, unknown>;
  searchedProjects: string[];
  skippedProjects: string[];
  codingProject?: string;
}> {
  const body: Record<string, unknown> = {
    limit: Math.min(Math.max(params.limit ?? 20, 1), 100),
    select: [
      "id",
      "trace_id",
      "name",
      "run_type",
      "status",
      "error",
      "start_time",
      "end_time",
      "extra",
      "total_tokens",
      "total_cost",
      "app_path",
      "session_id",
    ],
  };
  const { projectIds, searchedProjects, skippedProjects, codingProject } =
    await resolveLangsmithProjectIds(params, signal);
  if (projectIds.length > 0) body.session = projectIds;
  if (params.traceId) body.trace = params.traceId;
  if (params.runId) body.id = [params.runId];
  if (params.runType) body.run_type = params.runType;
  if (params.startTime) body.start_time = params.startTime;
  if (params.endTime) body.end_time = params.endTime;
  if (params.error === true) body.filter = 'eq(status, "error")';
  if (params.error === false) body.filter = 'neq(status, "error")';
  return { body, searchedProjects, skippedProjects, codingProject };
}

async function executeLangsmith(
  params: {
    action: LangsmithAction;
    runId?: string;
    traceId?: string;
    projectName?: string;
    projectNames?: string[];
    codingProject?: string;
    runType?: string;
    startTime?: string;
    endTime?: string;
    error?: boolean;
    limit?: number;
    output?: OutputMode;
    maxChars?: number;
  },
  signal?: AbortSignal,
): Promise<JsonValue> {
  const output = outputMode(params.output);
  const maxChars = defaultMaxChars(output, params.maxChars, 1_200, 2_000);

  if (params.action === "getRun") {
    if (!params.runId)
      throw new Error('langsmith action "getRun" requires runId.');
    const result = await fetchLangsmithRun(params.runId, signal);
    return compactLangsmithRun(result, {
      view: output === "verbose" ? "messages" : "summary",
      maxChars,
    });
  }

  const query = await langsmithQueryBody(params, signal);
  const result = await requestJson(new URL("/runs/query", LANGSMITH_API_BASE), {
    method: "POST",
    headers: langsmithHeaders(),
    body: JSON.stringify(query.body),
    signal,
  });
  return {
    codingProject: query.codingProject ?? null,
    searchedProjects: query.searchedProjects,
    skippedProjects: query.skippedProjects,
    runs: compactLangsmithRuns(result, maxChars),
  };
}

function parseSentryIssueReference(
  issueUrl?: string,
  issueId?: string,
  organizationSlug?: string,
  environment?: string,
): {
  issueId: string;
  organizationSlug: string;
  environment?: string;
} {
  let parsedIssueId = optionalString(issueId);
  let parsedOrgSlug = optionalString(
    organizationSlug ??
      process.env.SENTRY_ORG_SLUG ??
      process.env.SENTRY_ORGANIZATION_SLUG,
  );
  let parsedEnvironment = optionalString(environment);

  if (issueUrl) {
    const url = new URL(issueUrl);
    const issueMatch = url.pathname.match(/\/issues\/(\d+)/);
    if (issueMatch) parsedIssueId ??= issueMatch[1];
    parsedEnvironment ??= optionalString(url.searchParams.get("environment"));

    const hostParts = url.hostname.split(".");
    if (
      !parsedOrgSlug &&
      hostParts.length > 2 &&
      hostParts.at(-2) === "sentry" &&
      hostParts.at(-1) === "io"
    ) {
      parsedOrgSlug = hostParts[0];
    }

    const orgMatch = url.pathname.match(/\/organizations\/([^/]+)\//);
    if (!parsedOrgSlug && orgMatch) parsedOrgSlug = orgMatch[1];
  }

  if (!parsedIssueId)
    throw new Error("Missing Sentry issue id. Pass issueId or issueUrl.");
  if (!parsedOrgSlug)
    throw new Error(
      "Missing Sentry organization slug. Pass organizationSlug, set SENTRY_ORG_SLUG, or pass an org-subdomain issue URL.",
    );
  return {
    issueId: parsedIssueId,
    organizationSlug: parsedOrgSlug,
    environment: parsedEnvironment,
  };
}

function sentryUrl(pathname: string, query: Record<string, unknown> = {}): URL {
  const url = new URL(pathname, SENTRY_API_BASE);
  appendQuery(url, query);
  return url;
}

async function sentryGet(
  pathname: string,
  query: Record<string, unknown>,
  signal?: AbortSignal,
): Promise<JsonValue> {
  return requestJson(sentryUrl(pathname, query), {
    method: "GET",
    headers: sentryHeaders(),
    signal,
  });
}

function redactEmail(value: unknown): JsonValue | undefined {
  if (typeof value !== "string") return undefined;
  return value.replace(
    /([A-Z0-9._%+-]+)@([A-Z0-9.-]+\.[A-Z]{2,})/gi,
    "$1@email.com",
  );
}

function tagMap(tags: unknown): JsonObject {
  const result: JsonObject = {};
  if (!Array.isArray(tags)) return result;
  for (const tag of tags) {
    if (!isJsonObject(tag) || typeof tag.key !== "string") continue;
    result[tag.key] = previewValue(tag.value, 300);
  }
  return result;
}

function compactSentryUser(user: unknown): JsonValue {
  if (!isJsonObject(user)) return user == null ? null : previewValue(user, 400);
  return {
    id: user.id ?? null,
    username: redactEmail(user.username),
    name: user.name ?? null,
    email: redactEmail(user.email),
  };
}

function sanitizeSentryValue(value: unknown, maxChars: number): JsonValue {
  if (Array.isArray(value))
    return value.map((item) => sanitizeSentryValue(item, maxChars));
  if (!isJsonObject(value)) return previewValue(value, maxChars);

  const sanitized: JsonObject = {};
  for (const [key, nestedValue] of Object.entries(value)) {
    const lowerKey = key.toLowerCase();
    if (
      lowerKey.includes("authorization") ||
      lowerKey.includes("cookie") ||
      lowerKey.includes("token") ||
      lowerKey.includes("secret")
    ) {
      sanitized[key] = "[redacted]";
      continue;
    }
    sanitized[key] = sanitizeSentryValue(nestedValue, maxChars);
  }
  return previewValue(sanitized, maxChars);
}

function compactSentryIssue(issue: JsonValue, maxChars: number): JsonValue {
  const obj = asObject(issue);
  return {
    id: obj.id ?? null,
    shortId: obj.shortId ?? null,
    title: obj.title ?? null,
    culprit: truncateText(String(obj.culprit ?? ""), maxChars) ?? null,
    permalink: obj.permalink ?? null,
    level: obj.level ?? null,
    status: obj.status ?? null,
    substatus: obj.substatus ?? null,
    priority: obj.priority ?? null,
    count: obj.count ?? null,
    userCount: obj.userCount ?? null,
    firstSeen: obj.firstSeen ?? null,
    lastSeen: obj.lastSeen ?? null,
    project: obj.project ?? null,
    metadata: sanitizeSentryValue(obj.metadata, maxChars),
    assignedTo: sanitizeSentryValue(obj.assignedTo, maxChars),
    firstRelease: sanitizeSentryValue(obj.firstRelease, maxChars),
    lastRelease: sanitizeSentryValue(obj.lastRelease, maxChars),
    tags: Array.isArray(obj.tags) ? (obj.tags.slice(0, 20) as JsonValue[]) : [],
  };
}

function compactSentryFrame(frame: unknown, maxChars: number): JsonValue {
  const obj = asObject(frame as JsonValue);
  return {
    function: obj.function ?? null,
    module: obj.module ?? null,
    filename: obj.filename ?? null,
    absPath: truncateText(String(obj.absPath ?? ""), maxChars) ?? null,
    lineNo: obj.lineNo ?? null,
    colNo: obj.colNo ?? null,
    inApp: obj.inApp ?? null,
    context: previewValue(obj.context, maxChars),
  };
}

function compactSentryEntries(entries: unknown, maxChars: number): JsonObject {
  const result: JsonObject = {};
  if (!Array.isArray(entries)) return result;

  const exceptionEntry = entries.find(
    (entry) => isJsonObject(entry) && entry.type === "exception",
  );
  const values =
    isJsonObject(exceptionEntry) &&
    Array.isArray(asObject(exceptionEntry.data).values)
      ? (asObject(exceptionEntry.data).values as JsonValue[])
      : [];
  if (values.length > 0) {
    result.exceptions = values.map((value) => {
      const exception = asObject(value);
      const frames = Array.isArray(asObject(exception.stacktrace).frames)
        ? (asObject(exception.stacktrace).frames as JsonValue[])
        : [];
      const inAppFrames = frames.filter(
        (frame) => asObject(frame).inApp === true,
      );
      const selectedFrames = (
        inAppFrames.length > 0 ? inAppFrames : frames
      ).slice(-12);
      return {
        type: exception.type ?? null,
        value: truncateText(String(exception.value ?? ""), maxChars) ?? null,
        mechanism: sanitizeSentryValue(exception.mechanism, maxChars),
        frames: selectedFrames.map((frame) =>
          compactSentryFrame(frame, maxChars),
        ),
        omittedFrames: Math.max(0, frames.length - selectedFrames.length),
      };
    });
  }

  const breadcrumbEntry = entries.find(
    (entry) => isJsonObject(entry) && entry.type === "breadcrumbs",
  );
  const breadcrumbValues = isJsonObject(breadcrumbEntry)
    ? asObject(breadcrumbEntry.data).values
    : undefined;
  const breadcrumbs = Array.isArray(breadcrumbValues)
    ? (breadcrumbValues as JsonValue[])
    : [];
  if (breadcrumbs.length > 0) {
    result.breadcrumbs = breadcrumbs
      .slice(-20)
      .map((breadcrumb) =>
        sanitizeSentryValue(breadcrumb, maxChars),
      ) as JsonValue[];
    result.omittedBreadcrumbs = Math.max(0, breadcrumbs.length - 20);
  }

  const requestEntry = entries.find(
    (entry) => isJsonObject(entry) && entry.type === "request",
  );
  if (isJsonObject(requestEntry))
    result.request = sanitizeSentryValue(asObject(requestEntry.data), maxChars);

  return result;
}

function compactSentryEvent(event: JsonValue, maxChars: number): JsonValue {
  const obj = asObject(event);
  return {
    id: obj.id ?? null,
    eventID: obj.eventID ?? null,
    groupID: obj.groupID ?? null,
    title: obj.title ?? null,
    message: truncateText(String(obj.message ?? ""), maxChars) ?? null,
    type: obj.type ?? obj["event.type"] ?? null,
    platform: obj.platform ?? null,
    dateCreated: obj.dateCreated ?? null,
    dateReceived: obj.dateReceived ?? null,
    location: obj.location ?? null,
    culprit: truncateText(String(obj.culprit ?? ""), maxChars) ?? null,
    projectID: obj.projectID ?? null,
    metadata: sanitizeSentryValue(obj.metadata, maxChars),
    tags: tagMap(obj.tags),
    user: compactSentryUser(obj.user),
    errors: sanitizeSentryValue(obj.errors, maxChars),
    contexts: sanitizeSentryValue(obj.contexts, maxChars),
    context: sanitizeSentryValue(obj.context, maxChars),
    entries: compactSentryEntries(obj.entries, maxChars),
    release: sanitizeSentryValue(obj.release, maxChars),
    sdk: sanitizeSentryValue(obj.sdk, maxChars),
  };
}

function compactSentryEvents(
  value: JsonValue,
  maxChars: number,
  maxRows: number,
): JsonValue {
  const events = Array.isArray(value) ? value : [];
  return {
    events: events
      .slice(0, maxRows)
      .map((event) => compactSentryEvent(event, maxChars)),
    returned: events.length,
    omitted: Math.max(0, events.length - maxRows),
  };
}

async function executeSentry(
  params: {
    action: SentryAction;
    issueUrl?: string;
    organizationSlug?: string;
    issueId?: string;
    eventId?: string;
    environment?: string;
    statsPeriod?: string;
    start?: string;
    end?: string;
    query?: string;
    limit?: number;
    output?: OutputMode;
    maxRows?: number;
    maxChars?: number;
  },
  signal?: AbortSignal,
): Promise<JsonValue> {
  const output = outputMode(params.output);
  const maxChars = defaultMaxChars(output, params.maxChars, 800, 3_000);
  const maxRows = defaultMaxRows(output, params.maxRows, 5, 20);
  const issueRef = parseSentryIssueReference(
    params.issueUrl,
    params.issueId,
    params.organizationSlug,
    params.environment,
  );
  const issuePath = `/api/0/organizations/${encodeURIComponent(issueRef.organizationSlug)}/issues/${encodeURIComponent(issueRef.issueId)}/`;
  const commonQuery = { environment: issueRef.environment };

  if (params.action === "getIssue") {
    const issue = await sentryGet(issuePath, commonQuery, signal);
    return output === "verbose"
      ? sanitizeSentryValue(issue, maxChars)
      : compactSentryIssue(issue, maxChars);
  }

  if (params.action === "listIssueEvents") {
    const events = await sentryGet(
      `${issuePath}events/`,
      {
        ...commonQuery,
        start: params.start,
        end: params.end,
        statsPeriod: params.statsPeriod,
        query: params.query,
        full: output === "verbose" ? "1" : undefined,
      },
      signal,
    );
    return output === "verbose"
      ? compactSentryEvents(events, maxChars, maxRows)
      : compactSentryEvents(events, maxChars, maxRows);
  }

  const eventId = optionalString(params.eventId) ?? "latest";
  if (params.action === "getIssueEvent") {
    const event = await sentryGet(
      `${issuePath}events/${encodeURIComponent(eventId)}/`,
      commonQuery,
      signal,
    );
    return output === "verbose"
      ? sanitizeSentryValue(compactSentryEvent(event, maxChars), maxChars)
      : compactSentryEvent(event, maxChars);
  }

  const [issue, latestEvent, recentEvents] = await Promise.all([
    sentryGet(issuePath, commonQuery, signal),
    sentryGet(
      `${issuePath}events/${encodeURIComponent(eventId)}/`,
      commonQuery,
      signal,
    ),
    sentryGet(
      `${issuePath}events/`,
      {
        ...commonQuery,
        statsPeriod: params.statsPeriod ?? "24h",
        full: undefined,
      },
      signal,
    ),
  ]);

  return {
    issue: compactSentryIssue(issue, maxChars),
    selectedEvent: compactSentryEvent(latestEvent, maxChars),
    recentEvents: compactSentryEvents(recentEvents, maxChars, maxRows),
    source: {
      organizationSlug: issueRef.organizationSlug,
      issueId: issueRef.issueId,
      environment: issueRef.environment ?? null,
      eventId,
      apiBase: SENTRY_API_BASE,
    },
  };
}

type DebugObservabilityAction = "langsmithAxiom" | "sentryAxiomLangsmith";

type DebugOptions = {
  dataset?: string;
  padMinutes?: number;
  limit?: number;
  output?: OutputMode;
  maxRows?: number;
  maxChars?: number;
};

function debugLimits(options: DebugOptions): {
  output: OutputMode;
  maxChars: number;
  maxRows: number;
  limit: number;
} {
  const output = outputMode(options.output);
  return {
    output,
    maxChars: defaultMaxChars(output, options.maxChars, 600, 1_200),
    maxRows: defaultMaxRows(output, options.maxRows, 8, 20),
    limit: Math.min(
      Math.max(options.limit ?? (output === "verbose" ? 100 : 50), 1),
      1_000,
    ),
  };
}

async function debugLangsmithAxiom(
  params: DebugOptions & { runId: string },
  signal?: AbortSignal,
): Promise<JsonValue> {
  const { output, maxChars, maxRows, limit } = debugLimits(params);
  const run = await fetchLangsmithRun(params.runId, signal);
  const runSummary = compactLangsmithRun(run, {
    view: output === "verbose" ? "messages" : "summary",
    maxChars,
  });
  const runObj = asObject(runSummary);
  const metadata = asObject(runObj.metadata as JsonValue);
  const orgId = optionalString(metadata.orgId);
  const datasetName = axiomDatasetName(params.dataset);
  const padMinutes = params.padMinutes ?? 5;
  const padMs = Math.max(padMinutes, 0) * 60_000;
  const startTime = padIsoTime(runObj.startTime, -padMs);
  const endTime = padIsoTime(runObj.endTime, padMs);

  const exactApl = `${datasetApl(datasetName)} | where ${containsDataClause([params.runId])} | limit ${limit}`;
  const exactResult = await runAxiomApl(
    exactApl,
    { startTime, endTime },
    signal,
  );
  const exactSummary = compactAxiomResult(exactResult, {
    view: axiomViewForOutput(output),
    maxRows,
    maxChars,
  });

  const relatedValues = orgId ? [orgId, params.runId] : [params.runId];
  const relatedApl = `${datasetApl(datasetName)} | where ${containsDataClause(relatedValues)} | limit ${limit}`;
  const relatedResult = await runAxiomApl(
    relatedApl,
    { startTime, endTime },
    signal,
  );
  const relatedSummary = compactAxiomResult(relatedResult, {
    view: axiomViewForOutput(output),
    maxRows,
    maxChars,
  });

  return {
    langsmithRun: runSummary,
    axiom: {
      dataset: datasetName,
      window: { startTime, endTime, padMinutes },
      correlationKeys: { langsmithRunId: params.runId, orgId: orgId ?? null },
      exactLangsmithRunIdMatches: exactSummary,
      relatedLogs: relatedSummary,
      notes: orgId
        ? []
        : [
            "LangSmith run metadata did not include orgId; related Axiom search only used the LangSmith run id.",
          ],
    },
  };
}

function uniqueStrings(values: Array<unknown>): string[] {
  return [...new Set(values.map(optionalString).filter(Boolean) as string[])];
}

function extractSentryCorrelationKeys(event: JsonValue): JsonObject {
  const eventObj = asObject(event);
  const tags = tagMap(eventObj.tags);
  const contexts = asObject(eventObj.contexts as JsonValue);
  const trace = asObject(contexts.trace as JsonValue);
  const user = asObject(eventObj.user as JsonValue);

  return {
    sentryEventId: getFirst(eventObj.eventID, eventObj.id),
    sentryIssueId: eventObj.groupID,
    orgId: getFirst(
      tags.orgId,
      tags.org,
      asObject(contexts.organization as JsonValue).id,
    ),
    runId: tags.runId,
    requestId: tags.requestId,
    traceId: getFirst(trace.trace_id, tags.trace),
    userId: getFirst(user.id, tags.user),
    provider: tags.provider,
    capability: tags.capability,
    release: tags.release,
  };
}

async function debugSentryAxiomLangsmith(
  params: DebugOptions & {
    issueUrl?: string;
    organizationSlug?: string;
    issueId?: string;
    eventId?: string;
    environment?: string;
    statsPeriod?: string;
  },
  signal?: AbortSignal,
): Promise<JsonValue> {
  const { output, maxChars, maxRows, limit } = debugLimits(params);
  const issueRef = parseSentryIssueReference(
    params.issueUrl,
    params.issueId,
    params.organizationSlug,
    params.environment,
  );
  const issuePath = `/api/0/organizations/${encodeURIComponent(issueRef.organizationSlug)}/issues/${encodeURIComponent(issueRef.issueId)}/`;
  const commonQuery = { environment: issueRef.environment };
  const eventId = optionalString(params.eventId) ?? "latest";
  const [issue, event, recentEvents] = await Promise.all([
    sentryGet(issuePath, commonQuery, signal),
    sentryGet(
      `${issuePath}events/${encodeURIComponent(eventId)}/`,
      commonQuery,
      signal,
    ),
    sentryGet(
      `${issuePath}events/`,
      { ...commonQuery, statsPeriod: params.statsPeriod ?? "24h" },
      signal,
    ),
  ]);

  const correlationKeys = extractSentryCorrelationKeys(event);
  const runId = optionalString(correlationKeys.runId);
  const langsmith = runId
    ? await debugLangsmithAxiom({ ...params, runId }, signal).catch((err) => ({
        error: err instanceof Error ? err.message : String(err),
      }))
    : null;

  const datasetName = axiomDatasetName(params.dataset);
  const padMinutes = params.padMinutes ?? 10;
  const padMs = Math.max(padMinutes, 0) * 60_000;
  const startTime = padIsoTime(event && asObject(event).dateCreated, -padMs);
  const endTime = padIsoTime(event && asObject(event).dateCreated, padMs);
  const searchValues = uniqueStrings([
    correlationKeys.sentryEventId,
    correlationKeys.sentryIssueId,
    correlationKeys.orgId,
    correlationKeys.runId,
    correlationKeys.requestId,
    correlationKeys.traceId,
    correlationKeys.provider,
    correlationKeys.capability,
  ]);
  const axiomApl = `${datasetApl(datasetName)} | where ${containsDataClause(searchValues)} | limit ${limit}`;
  const axiomResult = searchValues.length
    ? await runAxiomApl(axiomApl, { startTime, endTime }, signal)
    : [];

  return {
    sentry: {
      issue: compactSentryIssue(issue, maxChars),
      selectedEvent: compactSentryEvent(event, maxChars),
      recentEvents: compactSentryEvents(recentEvents, maxChars, maxRows),
    },
    langsmith,
    axiom: {
      dataset: datasetName,
      window: { startTime, endTime, padMinutes },
      correlationKeys,
      searchValues,
      relatedLogs: compactAxiomResult(axiomResult, {
        view: axiomViewForOutput(output),
        maxRows,
        maxChars,
      }),
      apl: axiomApl,
    },
    source: {
      organizationSlug: issueRef.organizationSlug,
      issueId: issueRef.issueId,
      environment: issueRef.environment ?? null,
      eventId,
    },
  };
}

async function executeDebugObservability(
  params: DebugOptions & {
    action: DebugObservabilityAction;
    runId?: string;
    issueUrl?: string;
    organizationSlug?: string;
    issueId?: string;
    eventId?: string;
    environment?: string;
    statsPeriod?: string;
  },
  signal?: AbortSignal,
): Promise<JsonValue> {
  if (params.action === "langsmithAxiom") {
    if (!params.runId)
      throw new Error(
        'debug_observability action "langsmithAxiom" requires runId.',
      );
    return debugLangsmithAxiom({ ...params, runId: params.runId }, signal);
  }

  if (params.action === "sentryAxiomLangsmith") {
    return debugSentryAxiomLangsmith(params, signal);
  }

  throw new Error(`Unsupported debug_observability action: ${params.action}`);
}

type FreightDebugAction =
  | "findShipmentRun"
  | "langsmithFromAxiomRunId"
  | "explainBookingEvidence";

type FreightDebugParams = DebugOptions & {
  action?: FreightDebugAction;
  shipmentRef?: string;
  salesOrder?: string;
  vendor?: string;
  runId?: string;
  requestId?: string;
  startTime?: string;
  endTime?: string;
};

function rowLog(row: JsonObject): JsonObject {
  const data = asObject(row.data);
  if (data.message || data.runId || data.requestId || data.orgId) return data;
  return row;
}

function rowPayload(row: JsonObject): JsonObject {
  return asObject(rowLog(row).data);
}

function compactLineItems(payload: JsonObject): JsonValue {
  const requestBody = asObject(payload.requestBody);
  const lineItems = Array.isArray(requestBody.lineItems)
    ? requestBody.lineItems
    : Array.isArray(payload.lineItems)
      ? payload.lineItems
      : [];
  return lineItems.map((item, index) => {
    const obj = asObject(item as JsonValue);
    return {
      index,
      description: obj.description ?? null,
      freightClass: obj.freightClass ?? null,
      nmfcItemCode: obj.nmfcItemCode ?? null,
      nmfcSubCode: obj.nmfcSubCode ?? null,
      totalWeight: obj.totalWeight ?? null,
      dimensions: {
        length: obj.length ?? null,
        width: obj.width ?? null,
        height: obj.height ?? null,
      },
      pieces: obj.pieces ?? null,
      units: obj.units ?? null,
    };
  }) as JsonValue;
}

function compactFreightRow(row: JsonObject, maxChars: number): JsonObject {
  const log = rowLog(row);
  const payload = rowPayload(row);
  const requestBody = asObject(payload.requestBody);
  const responseBody = asObject(payload.responseBody);
  return {
    time: getFirst(row._time, log._time),
    message: getFirst(log.message, payload.code),
    requestId: log.requestId ?? null,
    runId: log.runId ?? null,
    orgId: log.orgId ?? null,
    code: payload.code ?? null,
    shipmentRef: getFirst(
      payload.shipmentRefNumber,
      payload.shipperReferenceNumber,
      requestBody.shipmentIdentifiers,
      responseBody.shipmentIdentifiers,
    ),
    vendor: getFirst(payload.vendor, payload.platform),
    carrier: getFirst(payload.carrierName, payload.carrierScac),
    price: payload.price ?? asObject(payload.responseBody).totalCost ?? null,
    quoteIndex: payload.quoteIndex ?? null,
    quoteId: getFirst(payload.quoteId, requestBody.quoteId),
    requestLineItems:
      Object.keys(requestBody).length > 0
        ? compactLineItems(payload)
        : undefined,
    identifiers: previewValue(
      getFirst(
        requestBody.shipmentIdentifiers,
        responseBody.shipmentIdentifiers,
      ),
      maxChars,
    ),
    payloadPreview: previewValue(payload, maxChars),
  };
}

function selectedFreightRows(rows: JsonObject[]): JsonObject[] {
  const interesting = rows.filter((row) => {
    const text = JSON.stringify(row);
    return /rate_booked|P1_DISPATCH|dispatchShipment|bookShipment|Starting runWilsonV3|Starting getRatesWorkflow|rate_quoted/i.test(
      text,
    );
  });
  return interesting.length > 0 ? interesting : rows;
}

async function fetchShipmentRows(
  params: FreightDebugParams,
  signal?: AbortSignal,
): Promise<{ dataset: string; apl: string; rows: JsonObject[] }> {
  const datasetName = axiomDatasetName(params.dataset);
  const primaryValues = uniqueStrings([
    params.shipmentRef,
    params.salesOrder,
    params.runId,
    params.requestId,
  ]);
  const searchValues =
    primaryValues.length > 0 ? primaryValues : uniqueStrings([params.vendor]);
  if (searchValues.length === 0) {
    throw new Error(
      "freight_debug requires at least one of shipmentRef, salesOrder, vendor, runId, or requestId.",
    );
  }
  const limit = Math.min(Math.max(params.limit ?? 200, 1), 500);
  const baseWhere = containsDataClause(searchValues);
  const vendorWhere = params.vendor
    ? ` and tostring(['data']) contains ${aplString(params.vendor)}`
    : "";
  const apl = `${datasetApl(datasetName)} | where ${baseWhere}${vendorWhere} | order by _time asc | limit ${limit}`;
  const result = await runAxiomApl(
    apl,
    { startTime: params.startTime, endTime: params.endTime },
    signal,
  );
  return { dataset: datasetName, apl, rows: extractAxiomRows(result) };
}

function chooseBookingRunId(rows: JsonObject[]): string | undefined {
  const booked = rows.find((row) =>
    JSON.stringify(row).includes("rate_booked"),
  );
  const p1 = rows.find((row) =>
    JSON.stringify(row).includes("P1_DISPATCH_RESPONSE"),
  );
  return optionalString(rowLog(booked ?? p1 ?? rows[0] ?? {}).runId);
}

async function executeFreightDebug(
  params: FreightDebugParams,
  signal?: AbortSignal,
): Promise<JsonValue> {
  const action = params.action ?? "findShipmentRun";
  const output = outputMode(params.output);
  const maxChars = defaultMaxChars(output, params.maxChars, 800, 1_500);
  const maxRows = defaultMaxRows(output, params.maxRows, 20, 40);

  if (action === "langsmithFromAxiomRunId") {
    if (!params.runId) throw new Error("Pass runId to fetch LangSmith.");
    return debugLangsmithAxiom(
      {
        ...params,
        runId: params.runId,
        output,
        maxRows,
        maxChars,
      },
      signal,
    );
  }

  const { dataset, apl, rows } = await fetchShipmentRows(params, signal);
  const selectedRows = selectedFreightRows(rows);
  const runId = chooseBookingRunId(selectedRows);
  const requestIds = uniqueStrings(
    selectedRows.map((row) => rowLog(row).requestId),
  );
  const runIds = uniqueStrings(selectedRows.map((row) => rowLog(row).runId));
  const compactRows = selectedRows
    .slice(0, maxRows)
    .map((row) => compactFreightRow(row, maxChars));

  const langsmith = runId
    ? await fetchLangsmithRun(runId, signal)
        .then((run) =>
          compactLangsmithRun(run, {
            view: output === "verbose" ? "messages" : "summary",
            maxChars,
          }),
        )
        .catch((err) => ({
          error: err instanceof Error ? err.message : String(err),
        }))
    : null;

  const dispatchRequestRows = selectedRows.filter((row) =>
    JSON.stringify(row).includes("P1_DISPATCH_REQUEST"),
  );
  const dispatchResponseRows = selectedRows.filter((row) =>
    JSON.stringify(row).includes("P1_DISPATCH_RESPONSE"),
  );
  const requestItems = dispatchRequestRows.flatMap((row) => {
    const items = compactLineItems(rowPayload(row));
    return Array.isArray(items) ? items : [];
  });
  const nullNmfcItems = requestItems.filter(
    (item) => isJsonObject(item) && item.nmfcItemCode == null,
  );
  const hasNmfcInContext = rows.some((row) =>
    /NMFC|nmfcItemCode|nmfcNumber/i.test(JSON.stringify(row)),
  );

  const evidence: JsonObject = {
    dataset,
    search: {
      shipmentRef: params.shipmentRef ?? null,
      salesOrder: params.salesOrder ?? null,
      vendor: params.vendor ?? null,
      startTime: params.startTime ?? null,
      endTime: params.endTime ?? null,
    },
    bestRunId: runId ?? null,
    runIds,
    requestIds,
    rowsMatched: rows.length,
    selectedRows: compactRows,
    omittedSelectedRows: Math.max(0, selectedRows.length - compactRows.length),
    langsmith,
    apl,
  };

  if (action === "explainBookingEvidence") {
    evidence.explanation = {
      finding:
        nullNmfcItems.length > 0
          ? "Provider dispatch line items had null nmfcItemCode."
          : "No null nmfcItemCode found in selected provider dispatch rows.",
      likelyCause:
        nullNmfcItems.length > 0 && hasNmfcInContext
          ? "The shipment context had NMFC evidence, but the provider booking request replayed quote-token line items that lacked the base NMFC item code. Compare selected quote-token/request rows against shipment commodity rows before editing code."
          : null,
      requestLineItems: requestItems,
      nullNmfcItemCount: nullNmfcItems.length,
      dispatchRequestCount: dispatchRequestRows.length,
      dispatchResponseCount: dispatchResponseRows.length,
    };
  }

  return evidence;
}

function recipeText(name: string, datasetName: string): string {
  const ds = datasetApl(datasetName);
  const recipes: Record<string, string> = {
    shipmentLifecycle: `${ds} | where tostring(['data']) contains '<SHP-REF>' or tostring(['data']) contains '<SO-NUMBER>' | project _time, data | order by _time asc | limit 100`,
    bookingEvent: `${ds} | where tostring(['data']) contains '<SHP-REF>' | where tostring(['data']) contains 'rate_booked' or tostring(['data']) contains 'DISPATCH' or tostring(['data']) contains 'bookShipment' | project _time, data | order by _time asc | limit 100`,
    providerRequestResponse: `${ds} | where tostring(['data']) contains '<REQUEST-ID>' | where tostring(['data']) contains 'REQUEST' or tostring(['data']) contains 'RESPONSE' | project _time, data | order by _time asc | limit 50`,
    correlateRun: `${ds} | where tostring(['data']) contains '<RUN-ID>' or tostring(['data']) contains '<REQUEST-ID>' | project _time, data | order by _time asc | limit 100`,
    nmfcBooking: `${ds} | where tostring(['data']) contains '<SHP-REF>' | where tostring(['data']) contains 'nmfc' or tostring(['data']) contains 'lineItems' or tostring(['data']) contains 'DISPATCH_REQUEST' | project _time, data | order by _time asc | limit 100`,
  };
  return (
    recipes[name] ??
    Object.entries(recipes)
      .map(([key, value]) => `${key}:\n${value}`)
      .join("\n\n")
  );
}

export default function observabilityTools(pi: ExtensionAPI) {
  pi.registerTool({
    name: "axiom",
    label: "Axiom",
    description:
      "Query Axiom logs/traces through one surface. Compact output summarizes useful info; verbose output returns capped raw rows.",
    promptSnippet: "Query Axiom logs/traces",
    promptGuidelines: [
      "Use axiom for Axiom logs/traces. Prefer output='compact' unless the user explicitly asks for verbose/raw details.",
      "Use action='apl' for APL and action='datasetQuery' for dataset query expressions.",
      "Never print Axiom API tokens; this tool reads AXIOM_API_TOKEN from the environment.",
    ],
    parameters: Type.Object({
      action: Type.Union([Type.Literal("apl"), Type.Literal("datasetQuery")], {
        description: "Axiom operation to run.",
      }),
      apl: Type.Optional(
        Type.String({
          description:
            "APL query. Required for action='apl'. Example: ['app'] | where ['level'] == 'error' | limit 20",
        }),
      ),
      dataset: Type.Optional(
        Type.String({
          description:
            "Dataset name. Defaults by detected coding project (cartage-agent→REDACTED-DATASET-NAME, ai-employees/agents→cartage-ai-employees), then AXIOM_DATASET. Used by action='datasetQuery' or inside your APL if supplied manually.",
        }),
      ),
      query: Type.Optional(
        Type.String({
          description:
            "Dataset query expression. Required for action='datasetQuery'.",
        }),
      ),
      startTime: Type.Optional(
        Type.String({
          description:
            "ISO timestamp or relative time accepted by Axiom, e.g. -1h",
        }),
      ),
      endTime: Type.Optional(
        Type.String({
          description:
            "ISO timestamp or relative time accepted by Axiom, e.g. now",
        }),
      ),
      includeCursor: Type.Optional(
        Type.Boolean({
          description:
            "For APL queries, ask Axiom to include a cursor when supported.",
        }),
      ),
      limit: Type.Optional(
        Type.Number({
          description:
            "Maximum rows requested from Axiom before tool-side compaction.",
        }),
      ),
      output: Type.Optional(
        Type.Union([Type.Literal("compact"), Type.Literal("verbose")], {
          description:
            "Output shape. Defaults to compact. Verbose is still capped.",
        }),
      ),
      maxRows: Type.Optional(
        Type.Number({
          description: "Maximum rows/samples returned after compaction.",
        }),
      ),
      maxChars: Type.Optional(
        Type.Number({ description: "Maximum characters per large field." }),
      ),
      selectFields: Type.Optional(
        Type.Array(Type.String(), {
          description:
            "Optional JSON/dot paths to return from each matched row instead of a summary, e.g. ['_time','data.message','data.runId','data.data.requestBody.lineItems'].",
        }),
      ),
    }),
    async execute(_toolCallId, params, signal) {
      const result = await executeAxiom(params, signal);
      return {
        content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
        details: { result },
      };
    },
  });

  pi.registerTool({
    name: "langsmith",
    label: "LangSmith",
    description:
      "Fetch or list LangSmith runs through one surface. Compact output returns useful summaries; verbose output returns capped messages/details.",
    promptSnippet: "Fetch/list LangSmith runs",
    promptGuidelines: [
      "Use langsmith for LangSmith runs/traces. Prefer output='compact' unless the user explicitly asks for verbose/raw details.",
      "Use action='getRun' for a known run id and action='listRuns' for trace/project/time filters. By default listRuns maps the current coding project to LangSmith (cartage-agent→agent-production, ai-employees→employees-production), then falls back to known production projects. Use projectName/projectNames to override or codingProject to choose a mapped codebase explicitly.",
      "Do not call langsmith after debug_observability unless the user asks for deeper trace inspection.",
      "Never print LangSmith API keys; this tool reads LANGSMITH_API_KEY from the environment.",
    ],
    parameters: Type.Object({
      action: Type.Union([Type.Literal("getRun"), Type.Literal("listRuns")], {
        description: "LangSmith operation to run.",
      }),
      runId: Type.Optional(
        Type.String({
          description:
            "Run UUID. Required for action='getRun'; optional filter for action='listRuns'.",
        }),
      ),
      traceId: Type.Optional(
        Type.String({
          description: "Trace UUID filter for action='listRuns'.",
        }),
      ),
      projectName: Type.Optional(
        Type.String({
          description:
            "LangSmith project/session name or id. Comma-separated names are accepted.",
        }),
      ),
      projectNames: Type.Optional(
        Type.Array(Type.String(), {
          description:
            "LangSmith project/session names or ids to search together. Overrides coding-project mapping. Defaults map cwd when recognized, otherwise include agent-production and employees-production when available.",
        }),
      ),
      codingProject: Type.Optional(
        Type.String({
          description:
            "Coding project key to map to LangSmith projects, e.g. cartage-agent -> agent-production, ai-employees -> employees-production. Defaults to current cwd detection.",
        }),
      ),
      runType: Type.Optional(
        Type.String({
          description: "Run type filter, e.g. llm, chain, tool, retriever.",
        }),
      ),
      startTime: Type.Optional(
        Type.String({ description: "Earliest start_time ISO timestamp." }),
      ),
      endTime: Type.Optional(
        Type.String({ description: "Latest start_time ISO timestamp." }),
      ),
      error: Type.Optional(
        Type.Boolean({
          description: "Filter to errored/non-errored runs when supported.",
        }),
      ),
      limit: Type.Optional(
        Type.Number({
          description:
            "Maximum runs to return for action='listRuns'. Defaults to 20, max 100.",
        }),
      ),
      output: Type.Optional(
        Type.Union([Type.Literal("compact"), Type.Literal("verbose")], {
          description:
            "Output shape. Defaults to compact. Verbose is still capped.",
        }),
      ),
      maxChars: Type.Optional(
        Type.Number({
          description: "Maximum characters per large text/blob preview.",
        }),
      ),
    }),
    async execute(_toolCallId, params, signal) {
      const result = await executeLangsmith(params, signal);
      return {
        content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
        details: { result },
      };
    },
  });

  pi.registerTool({
    name: "sentry",
    label: "Sentry",
    description:
      "Fetch Sentry issue and event debug information via the Sentry API. Reads SENTRY_AUTH_TOKEN from the environment.",
    promptSnippet: "Fetch Sentry issue/event details for debugging",
    promptGuidelines: [
      "Use sentry when the user provides a Sentry issue URL or asks for Sentry issue debug information.",
      "Prefer action='debugIssue' for a first pass; it returns issue metadata, the selected event, stack frames, breadcrumbs, request details, and recent events.",
      "Use action='getIssueEvent' with eventId='latest', 'oldest', or 'recommended' when you need one full event-oriented summary.",
      "Never print Sentry API tokens; this tool reads SENTRY_AUTH_TOKEN from the environment. SENTRY_API_TOKEN and SENTRY_TOKEN are accepted aliases.",
    ],
    parameters: Type.Object({
      action: Type.Union(
        [
          Type.Literal("getIssue"),
          Type.Literal("listIssueEvents"),
          Type.Literal("getIssueEvent"),
          Type.Literal("debugIssue"),
        ],
        { description: "Sentry operation to run." },
      ),
      issueUrl: Type.Optional(
        Type.String({
          description:
            "Full Sentry issue URL. The tool extracts organization slug, issue id, and environment when present.",
        }),
      ),
      organizationSlug: Type.Optional(
        Type.String({
          description:
            "Sentry organization slug. Defaults to SENTRY_ORG_SLUG/SENTRY_ORGANIZATION_SLUG or org subdomain from issueUrl.",
        }),
      ),
      issueId: Type.Optional(
        Type.String({
          description:
            "Sentry issue/group id, e.g. 7514902006. Required if issueUrl is not provided.",
        }),
      ),
      eventId: Type.Optional(
        Type.String({
          description:
            "Event id, or one of latest, oldest, recommended. Defaults to latest.",
        }),
      ),
      environment: Type.Optional(
        Type.String({
          description:
            "Environment filter, e.g. production. Defaults to environment query param from issueUrl.",
        }),
      ),
      statsPeriod: Type.Optional(
        Type.String({
          description: "Relative period for event listing, e.g. 24h, 7d, 14d.",
        }),
      ),
      start: Type.Optional(
        Type.String({
          description: "ISO-8601 start time for listIssueEvents.",
        }),
      ),
      end: Type.Optional(
        Type.String({ description: "ISO-8601 end time for listIssueEvents." }),
      ),
      query: Type.Optional(
        Type.String({
          description: "Sentry event search query for listIssueEvents.",
        }),
      ),
      output: Type.Optional(
        Type.Union([Type.Literal("compact"), Type.Literal("verbose")], {
          description:
            "Output shape. Defaults to compact. Verbose is still sanitized and capped.",
        }),
      ),
      maxRows: Type.Optional(
        Type.Number({
          description: "Maximum event rows/samples returned after compaction.",
        }),
      ),
      maxChars: Type.Optional(
        Type.Number({ description: "Maximum characters per large field." }),
      ),
    }),
    async execute(_toolCallId, params, signal) {
      const result = await executeSentry(params, signal);
      return {
        content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
        details: { result },
      };
    },
  });

  pi.registerTool({
    name: "debug_observability",
    label: "Debug Observability",
    description:
      "Composable parent observability workflow. Correlates Sentry issues, LangSmith runs, and Axiom logs in one compact report.",
    promptSnippet: "Debug across Sentry, LangSmith, and Axiom",
    promptGuidelines: [
      "Use debug_observability action='sentryAxiomLangsmith' when the user provides a Sentry issue URL or asks for a combined production debug workflow.",
      "Use debug_observability action='langsmithAxiom' when the user provides only a LangSmith run id.",
      "This parent tool already composes Sentry, LangSmith, and Axiom; do not follow it with child tools unless the user asks for deeper inspection.",
      "Prefer output='compact'. Use output='verbose' only when explicitly requested.",
      "Never print Axiom, LangSmith, or Sentry API tokens.",
    ],
    parameters: Type.Object({
      action: Type.Optional(
        Type.Union(
          [
            Type.Literal("langsmithAxiom"),
            Type.Literal("sentryAxiomLangsmith"),
          ],
          {
            description:
              "Debug workflow. Defaults to sentryAxiomLangsmith when issueUrl/issueId is provided, otherwise langsmithAxiom.",
          },
        ),
      ),
      runId: Type.Optional(Type.String({ description: "LangSmith run UUID." })),
      issueUrl: Type.Optional(
        Type.String({
          description:
            "Full Sentry issue URL for sentryAxiomLangsmith. Extracts org slug, issue id, and environment when present.",
        }),
      ),
      organizationSlug: Type.Optional(
        Type.String({ description: "Sentry organization slug." }),
      ),
      issueId: Type.Optional(
        Type.String({ description: "Sentry issue/group id." }),
      ),
      eventId: Type.Optional(
        Type.String({
          description:
            "Sentry event id, or latest/oldest/recommended. Defaults to latest.",
        }),
      ),
      environment: Type.Optional(
        Type.String({
          description: "Sentry environment filter, e.g. production.",
        }),
      ),
      statsPeriod: Type.Optional(
        Type.String({
          description: "Sentry recent-events period, e.g. 24h, 7d.",
        }),
      ),
      dataset: Type.Optional(
        Type.String({
          description:
            "Axiom dataset name. Defaults by detected coding project, then AXIOM_DATASET.",
        }),
      ),
      padMinutes: Type.Optional(
        Type.Number({
          description:
            "Minutes to pad before/after the LangSmith run window. Defaults to 5.",
        }),
      ),
      limit: Type.Optional(
        Type.Number({
          description:
            "Maximum Axiom rows requested per query. Defaults to 50 compact / 100 verbose.",
        }),
      ),
      output: Type.Optional(
        Type.Union([Type.Literal("compact"), Type.Literal("verbose")], {
          description:
            "Output shape. Defaults to compact. Verbose is still capped.",
        }),
      ),
      maxRows: Type.Optional(
        Type.Number({
          description: "Maximum timeline/raw rows in each Axiom summary.",
        }),
      ),
      maxChars: Type.Optional(
        Type.Number({ description: "Maximum characters per large field." }),
      ),
    }),
    async execute(_toolCallId, params, signal) {
      const defaultAction =
        params.issueUrl || params.issueId
          ? "sentryAxiomLangsmith"
          : "langsmithAxiom";
      const result = await executeDebugObservability(
        { ...params, action: params.action ?? defaultAction },
        signal,
      );
      return {
        content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
        details: { result },
      };
    },
  });

  pi.registerTool({
    name: "freight_debug",
    label: "Freight Debug",
    description:
      "Parent workflow for freight/shipment observability. Finds booking/rate runs, fetches correlated LangSmith, and summarizes provider request evidence without giant raw logs.",
    promptSnippet: "Find freight shipment booking/rate run and evidence",
    promptGuidelines: [
      "Use freight_debug before raw Axiom/LangSmith when the user asks to find a run for a shipment, sales order, carrier booking, or freight provider issue.",
      "Use action='findShipmentRun' for run discovery, action='explainBookingEvidence' for field mismatch questions like missing NMFC, and action='langsmithFromAxiomRunId' when you already have an Axiom/LangSmith run id.",
      "The tool strips noisy execution summaries and redacts tokens; use raw axiom only for deeper inspection after this summary.",
    ],
    parameters: Type.Object({
      action: Type.Optional(
        Type.Union(
          [
            Type.Literal("findShipmentRun"),
            Type.Literal("langsmithFromAxiomRunId"),
            Type.Literal("explainBookingEvidence"),
          ],
          {
            description: "Freight debug workflow. Defaults to findShipmentRun.",
          },
        ),
      ),
      shipmentRef: Type.Optional(
        Type.String({ description: "Shipment reference, e.g. SHP-094." }),
      ),
      salesOrder: Type.Optional(
        Type.String({ description: "Sales order / PO, e.g. SO13093." }),
      ),
      vendor: Type.Optional(
        Type.String({
          description: "Provider/vendor hint, e.g. priority1 or P1.",
        }),
      ),
      runId: Type.Optional(
        Type.String({ description: "Axiom/LangSmith run id to correlate." }),
      ),
      requestId: Type.Optional(
        Type.String({ description: "Request id to correlate." }),
      ),
      startTime: Type.Optional(
        Type.String({ description: "Optional Axiom startTime." }),
      ),
      endTime: Type.Optional(
        Type.String({ description: "Optional Axiom endTime." }),
      ),
      dataset: Type.Optional(
        Type.String({
          description:
            "Axiom dataset. Defaults by detected coding project, then AXIOM_DATASET.",
        }),
      ),
      limit: Type.Optional(
        Type.Number({ description: "Max Axiom rows to request." }),
      ),
      output: Type.Optional(
        Type.Union([Type.Literal("compact"), Type.Literal("verbose")], {
          description: "Output shape. Defaults to compact.",
        }),
      ),
      maxRows: Type.Optional(
        Type.Number({ description: "Max selected rows returned." }),
      ),
      maxChars: Type.Optional(
        Type.Number({ description: "Max chars per preview field." }),
      ),
    }),
    async execute(_toolCallId, params, signal) {
      const result = await executeFreightDebug(params, signal);
      return {
        content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
        details: { result },
      };
    },
  });

  pi.registerTool({
    name: "observability_recipe",
    label: "Observability Recipe",
    description:
      "Return saved Axiom query recipes for common production-debug workflows without spending context on failed query attempts.",
    promptSnippet: "Get saved Axiom query recipes",
    promptGuidelines: [
      "Use observability_recipe when you need a common Axiom query shape: shipment lifecycle, booking event, provider request/response, run correlation, or NMFC booking evidence.",
      "Prefer freight_debug for executed freight investigations; recipes are for custom follow-up queries.",
    ],
    parameters: Type.Object({
      name: Type.Optional(
        Type.Union(
          [
            Type.Literal("shipmentLifecycle"),
            Type.Literal("bookingEvent"),
            Type.Literal("providerRequestResponse"),
            Type.Literal("correlateRun"),
            Type.Literal("nmfcBooking"),
          ],
          { description: "Recipe name. Omit to list all recipes." },
        ),
      ),
      dataset: Type.Optional(
        Type.String({
          description:
            "Dataset name. Defaults by detected coding project, then AXIOM_DATASET.",
        }),
      ),
    }),
    async execute(_toolCallId, params) {
      const datasetName = axiomDatasetName(params.dataset);
      const result = recipeText(params.name ?? "all", datasetName);
      return {
        content: [{ type: "text", text: result }],
        details: { result },
      };
    },
  });

  pi.registerCommand("observability-status", {
    description:
      "Show whether Axiom and LangSmith environment variables are configured.",
    handler: async (_args, ctx) => {
      const lines = [
        `Axiom: ${process.env.AXIOM_API_TOKEN ? "AXIOM_API_TOKEN set" : "missing AXIOM_API_TOKEN"}, dataset ${axiomDatasetDisplay()}, org/project ${process.env.AXIOM_ORG_ID ?? process.env.AXIOM_PROJECT_ID ?? "cartage-q438"}`,
        `LangSmith: ${process.env.LANGSMITH_API_KEY ? "LANGSMITH_API_KEY set" : "missing LANGSMITH_API_KEY"}`,
        `Sentry: ${process.env.SENTRY_AUTH_TOKEN ? "SENTRY_AUTH_TOKEN set" : "missing SENTRY_AUTH_TOKEN"}, org ${process.env.SENTRY_ORG_SLUG ?? process.env.SENTRY_ORGANIZATION_SLUG ?? "from issue URL"}`,
        `Bases: AXIOM_API_BASE=${AXIOM_API_BASE}, LANGSMITH_ENDPOINT=${LANGSMITH_API_BASE}, SENTRY_API_BASE=${SENTRY_API_BASE}`,
      ];
      ctx.ui.notify(lines.join("\n"), "info");
    },
  });
}
