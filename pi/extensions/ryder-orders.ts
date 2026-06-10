import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { Type } from "@earendil-works/pi-ai";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

/**
 * ryder_orders — fetch Ryder Last Mile (RLM) order status via the prod
 * order-status API. Defaults target the Sundays account (partnerId=Cartage,
 * clientId=SUNDAYS). Credentials read from ~/.pi/agent/.env
 * (RYDER_SUBSCRIPTION_KEY); the key is never printed.
 *
 * RLM list returns the client's OPEN orders only (~25 cap); closed/aged
 * orders drop off. One orderNumber can appear as multiple legs (distinct
 * lobTracking), so results are keyed per leg.
 */

type RyderOrdersInput = {
  action: "list" | "order" | "exceptions";
  partnerId?: string;
  clientId?: string;
  orderRef?: string;
  raw?: boolean;
  redactPii?: boolean;
};

const DEFAULT_PARTNER_ID = "Cartage";
const DEFAULT_CLIENT_ID = "SUNDAYS";

const BASE_URL: Record<string, string> = {
  prod: "https://api.ryder.com",
  qa: "https://apiqa.ryder.com",
};

const envPaths = [
  process.env.RYDER_PI_ENV_FILE ?? "",
  join(process.env.HOME ?? "", ".pi/agent/.env.local"),
  join(process.env.HOME ?? "", ".pi/agent/.env"),
  join(process.env.HOME ?? "", ".pi/.env"),
].filter(Boolean);

// Mirror of src/server/services/RyderService/statusCodes.constants.ts buckets.
const MILESTONE_BUCKET: Record<string, string> = {
  CANC: "canceled",
  CPD: "canceled",
  ECAN: "canceled",
  DLVD: "delivered",
  EXCM: "delivered",
  PDLVD: "delivered",
  PEXCM: "delivered",
  PICK: "delivered",
  PPICK: "delivered",
  DSCH: "scheduled",
  FODT: "scheduled",
  PDSCH: "scheduled",
  RPLN: "scheduled",
  RSCH: "scheduled",
  HOLD: "held",
  RFSD: "exception",
  UNSC: "exception",
  PRCVD: "in_transit",
  RCVD: "in_transit",
  SDTP: "in_transit",
  SETA: "in_transit",
  SFTP: "in_transit",
  SORG: "in_transit",
};

// Tier-2 incident event codes (base-code prefix unless an exact slash code).
const INCIDENT_BASE = new Set([
  "SHRT",
  "RSHO",
  "DMGD",
  "DDLX",
  "DIHD",
  "DREF",
  "DCNC",
  "DCAN",
  "DNAH",
  "DUDM",
]);
const INCIDENT_EXACT = new Set([
  "DLVD/DWE",
  "DLVD/DPR",
  "RSCH/MTW",
  "UNSC/MTW",
  "DASH/SC3",
  "DASH/SC4",
  "DASH/SC5",
]);

export default function ryderOrders(pi: ExtensionAPI) {
  pi.registerTool({
    name: "ryder_orders",
    label: "Ryder Orders",
    description:
      "Fetch Ryder Last Mile (RLM) order status. Defaults to the Sundays account. " +
      "action=list (open orders), order (single by orderRef), exceptions (held/exception/incident legs only).",
    promptSnippet:
      "Fetch Ryder RLM order status (defaults to Sundays). Credentials from ~/.pi/agent/.env.",
    promptGuidelines: [
      "Use ryder_orders to pull live Ryder last-mile order status; defaults partnerId=Cartage, clientId=SUNDAYS.",
      "action=exceptions returns only held/exception/incident legs (keyed per lobTracking).",
      "Never print the Ryder subscription key; it is read from ~/.pi/agent/.env. Consignee PII is redacted unless redactPii=false.",
    ],
    parameters: Type.Object({
      action: Type.Union([
        Type.Literal("list"),
        Type.Literal("order"),
        Type.Literal("exceptions"),
      ]),
      partnerId: Type.Optional(
        Type.String({ description: "Ryder partnerId. Default 'Cartage'." }),
      ),
      clientId: Type.Optional(
        Type.String({
          description:
            "Ryder clientId (= integration enterpriseClientID). Default 'SUNDAYS'.",
        }),
      ),
      orderRef: Type.Optional(
        Type.String({ description: "Order reference for action=order." }),
      ),
      raw: Type.Optional(
        Type.Boolean({
          description: "Return full raw order JSON instead of a summary.",
        }),
      ),
      redactPii: Type.Optional(
        Type.Boolean({
          description: "Redact consignee PII (name/address/email/phone). Default true.",
        }),
      ),
    }),
    async execute(_toolCallId, params: RyderOrdersInput, signal) {
      const subscriptionKey =
        readEnvValue("RYDER_SUBSCRIPTION_KEY") ?? readEnvValue("RYDER_API_KEY");
      if (!subscriptionKey) {
        return errorResult(
          "Missing RYDER_SUBSCRIPTION_KEY in ~/.pi/agent/.env (or process env). Add it, then /reload.",
        );
      }
      const environment = (readEnvValue("RYDER_ENV") ?? "prod").toLowerCase();
      const base = BASE_URL[environment] ?? BASE_URL.prod;
      const redactPii = params.redactPii !== false;

      const query: Record<string, string> = {};
      if (params.action === "order") {
        if (!params.orderRef)
          return errorResult("action=order requires orderRef.");
        query.orderRef = params.orderRef;
      } else {
        query.partnerId = params.partnerId ?? DEFAULT_PARTNER_ID;
        query.clientId = params.clientId ?? DEFAULT_CLIENT_ID;
      }

      const res = await fetchRyder({
        base,
        subscriptionKey,
        query,
        signal,
      });

      if (!res.ok) {
        return errorResult(
          `Ryder ${params.action}: HTTP ${res.status} — ${truncate(stringify(res.data), 400)}`,
        );
      }

      const orders = Array.isArray(res.data) ? res.data : [];
      if (typeof res.data === "string") {
        // API returns a bare string message (e.g. "No Order is found ...").
        return compactResult({
          text: `Ryder ${params.action}: ${res.data}`,
          details: { ok: true, status: res.status, message: res.data },
        });
      }

      const legs = orders
        .map((o) => summarizeLeg(o))
        .filter((leg): leg is LegSummary => leg !== undefined)
        .map((leg) => (redactPii ? leg : withPii(leg, orders)));

      const filtered =
        params.action === "exceptions" ? legs.filter((l) => l.isException) : legs;

      if (params.raw) {
        const rawData = redactPii ? redactConsignee(res.data) : res.data;
        return compactResult({
          text: `Ryder ${params.action}: ${filtered.length}/${legs.length} legs (HTTP ${res.status}).\n\n${stringify(rawData)}`,
          details: { ok: true, status: res.status, count: filtered.length, data: rawData },
        });
      }

      return compactResult({
        text: formatLegs(params.action, res.status, filtered, legs.length),
        details: {
          ok: true,
          status: res.status,
          partnerId: query.partnerId,
          clientId: query.clientId,
          totalLegs: legs.length,
          returnedLegs: filtered.length,
          legs: filtered,
        },
      });
    },
  });
}

type LegSummary = {
  orderNumber?: string;
  lobTracking?: string;
  statusCode?: string;
  statusDescription?: string;
  bucket: string;
  asOf?: string;
  incidentEvents: Array<{ code: string; reason?: string; description?: string; when?: string }>;
  isException: boolean;
};

function summarizeLeg(order: unknown): LegSummary | undefined {
  if (!isRecord(order)) return undefined;
  const oi = recordValue(order, "orderInfo");
  const cos = recordValue(oi, "currentOrderStatus");
  const code = stringValue(cos, "statusCode");
  const bucket = code ? (MILESTONE_BUCKET[code] ?? "other") : "other";

  const incidentEvents: LegSummary["incidentEvents"] = [];
  const shipments = Array.isArray(order["shipmentInfo"]) ? order["shipmentInfo"] : [];
  for (const s of shipments) {
    if (!isRecord(s)) continue;
    const events = Array.isArray(s["events"]) ? s["events"] : [];
    for (const e of events) {
      if (!isRecord(e)) continue;
      const ec = stringValue(e, "code");
      if (!ec || !isIncident(ec)) continue;
      incidentEvents.push({
        code: ec,
        reason: stringValue(e, "reason") || undefined,
        description: stringValue(e, "description") || undefined,
        when: stringValue(e, "dateTime") || undefined,
      });
    }
  }

  const isException =
    bucket === "exception" || bucket === "held" || incidentEvents.length > 0;

  return {
    orderNumber: stringValue(oi, "orderNumber"),
    lobTracking: stringValue(oi, "lobTracking") ?? stringValue(order, "lobParentTracking"),
    statusCode: code,
    statusDescription: stringValue(cos, "description"),
    bucket,
    asOf: stringValue(cos, "dateTime"),
    incidentEvents,
    isException,
  };
}

function withPii(leg: LegSummary, _orders: unknown[]): LegSummary {
  return leg; // summary already carries no PII; raw mode handles full payload
}

function isIncident(code: string): boolean {
  if (INCIDENT_EXACT.has(code)) return true;
  const base = code.split("/")[0];
  return INCIDENT_BASE.has(base);
}

async function fetchRyder(input: {
  base: string;
  subscriptionKey: string;
  query: Record<string, string>;
  signal?: AbortSignal;
}) {
  const url = new URL(`${input.base}/rcsc/order-status/v1/orders`);
  for (const [k, v] of Object.entries(input.query)) url.searchParams.set(k, v);
  const response = await fetch(url, {
    method: "GET",
    headers: {
      Accept: "application/json",
      "Ocp-Apim-Subscription-Key": input.subscriptionKey,
    },
    signal: input.signal,
  });
  const text = await response.text();
  return { ok: response.ok, status: response.status, data: parseJsonOrText(text) };
}

function formatLegs(
  action: string,
  status: number,
  legs: LegSummary[],
  total: number,
): string {
  const header = `Ryder ${action}: HTTP ${status} — ${legs.length}${
    action === "exceptions" ? `/${total} exception` : ""
  } leg(s)`;
  if (legs.length === 0)
    return `${header}\n(none)${action === "exceptions" && total > 0 ? ` — ${total} open legs, all healthy` : ""}`;
  const lines = legs.map((l) => {
    const inc =
      l.incidentEvents.length > 0
        ? `  | incidents: ${l.incidentEvents
            .map((e) => `${e.code}${e.reason ? "/" + e.reason : ""}`)
            .join(", ")}`
        : "";
    return `  • ${l.orderNumber ?? "?"} [${l.lobTracking ?? "?"}]  ${l.statusCode ?? "?"} (${l.bucket})  ${l.statusDescription ?? ""}  @ ${l.asOf ?? "?"}${inc}`;
  });
  return `${header}\n${lines.join("\n")}`;
}

function readEnvValue(key: string): string | undefined {
  if (process.env[key]) return process.env[key];
  for (const path of envPaths) {
    if (!existsSync(path)) continue;
    for (const line of readFileSync(path, "utf8").split(/\r?\n/)) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith("#")) continue;
      const sep = trimmed.indexOf("=");
      if (sep < 0) continue;
      if (trimmed.slice(0, sep).trim() !== key) continue;
      return unquote(trimmed.slice(sep + 1).trim());
    }
  }
  return undefined;
}

function unquote(v: string): string {
  if ((v.startsWith('"') && v.endsWith('"')) || (v.startsWith("'") && v.endsWith("'")))
    return v.slice(1, -1);
  return v;
}

function redactConsignee(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(redactConsignee);
  if (!isRecord(value)) return value;
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(value)) {
    if (k === "consigneeInfo" && isRecord(v)) {
      out[k] = { ...v, name: "[REDACTED]", address1: "[REDACTED]", address2: "[REDACTED]", email: "[REDACTED]", primaryContact: "[REDACTED]", cell: "[REDACTED]", alternatePhone: "[REDACTED]", officePhone: "[REDACTED]" };
    } else {
      out[k] = redactConsignee(v);
    }
  }
  return out;
}

function compactResult(input: { text: string; details: unknown }) {
  return { content: [{ type: "text" as const, text: input.text }], details: input.details };
}

function errorResult(message: string) {
  return { content: [{ type: "text" as const, text: message }], details: { message }, isError: true };
}

function parseJsonOrText(text: string): unknown {
  if (!text) return undefined;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return text;
  }
}

function stringify(value: unknown): string {
  return typeof value === "string" ? value : JSON.stringify(value, null, 2);
}

function truncate(s: string, n: number): string {
  return s.length > n ? `${s.slice(0, n)}…` : s;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function recordValue(value: unknown, key: string): Record<string, unknown> | undefined {
  if (!isRecord(value)) return undefined;
  const child = value[key];
  return isRecord(child) ? child : undefined;
}

function stringValue(value: unknown, key: string): string | undefined {
  if (!isRecord(value)) return undefined;
  const child = value[key];
  return typeof child === "string" ? child : undefined;
}
