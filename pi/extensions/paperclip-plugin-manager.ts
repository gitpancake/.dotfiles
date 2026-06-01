import fs from "node:fs";
import os from "node:os";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

type Json = null | boolean | number | string | Json[] | { [key: string]: Json };
type JsonObject = { [key: string]: Json };

type PluginRecord = {
  id: string;
  pluginKey: string;
  packageName: string;
  version: string;
  status: string;
  lastError?: string | null;
  manifestJson?: { version?: string; capabilities?: string[]; instanceConfigSchema?: JsonObject } | null;
};

type PluginConfigRecord = {
  id: string;
  pluginId: string;
  configJson: JsonObject;
  lastError?: string | null;
};

const DEFAULT_API_BASE = "https://paperclip-production-30dec.up.railway.app";

type PluginAction = "install" | "upgrade" | "replace" | "remove" | "inspect" | "config";

function asObject(value: unknown): JsonObject {
  return value && typeof value === "object" && !Array.isArray(value) ? value as JsonObject : {};
}

function readAuthToken(apiBase: string): string | null {
  const authPath = `${os.homedir()}/.paperclip/auth.json`;
  if (!fs.existsSync(authPath)) return null;
  const raw = JSON.parse(fs.readFileSync(authPath, "utf8")) as { credentials?: Record<string, { token?: string }> };
  const normalized = apiBase.replace(/\/$/, "");
  return raw.credentials?.[normalized]?.token ?? null;
}

function resolveApiBase(params: { apiBase?: string | null }): string {
  return (params.apiBase?.trim() || process.env.PAPERCLIP_API_BASE || process.env.PAPERCLIP_URL || DEFAULT_API_BASE).replace(/\/$/, "");
}

function resolveToken(apiBase: string, params: { token?: string | null }): string {
  const token = params.token?.trim() || process.env.PAPERCLIP_BOARD_TOKEN || process.env.PAPERCLIP_API_KEY || readAuthToken(apiBase);
  if (!token) {
    throw new Error(`No Paperclip token found. Pass token, set PAPERCLIP_BOARD_TOKEN, or login so ~/.paperclip/auth.json contains ${apiBase}.`);
  }
  return token;
}

async function readJson(response: Response): Promise<Json> {
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text) as Json;
  } catch {
    return text;
  }
}

async function paperclipFetch(apiBase: string, token: string, path: string, init: RequestInit = {}): Promise<Json> {
  const response = await fetch(`${apiBase}${path}`, {
    ...init,
    headers: {
      authorization: `Bearer ${token}`,
      "content-type": "application/json",
      ...(init.headers ?? {}),
    },
  });
  const body = await readJson(response);
  if (!response.ok) {
    const detail = typeof body === "string" ? body : JSON.stringify(body);
    throw new Error(`Paperclip ${init.method ?? "GET"} ${path} failed: HTTP ${response.status} ${detail}`);
  }
  return body;
}

function compactPlugin(value: Json): JsonObject {
  const plugin = asObject(value);
  const manifest = asObject(plugin.manifestJson);
  return {
    id: plugin.id ?? null,
    pluginKey: plugin.pluginKey ?? null,
    packageName: plugin.packageName ?? null,
    version: plugin.version ?? null,
    manifestVersion: manifest.version ?? null,
    status: plugin.status ?? null,
    lastError: plugin.lastError ?? null,
    capabilities: Array.isArray(manifest.capabilities) ? manifest.capabilities as Json : [],
    updatedAt: plugin.updatedAt ?? null,
  };
}

function redactConfig(config: JsonObject | null): JsonObject | null {
  if (!config) return null;
  const redact = (value: Json, path: string[] = []): Json => {
    if (Array.isArray(value)) return value.map((item, index) => redact(item, [...path, String(index)]));
    if (!value || typeof value !== "object") return value;
    const out: JsonObject = {};
    for (const [key, child] of Object.entries(value)) {
      if (/token|secret|password|key/i.test(key) && typeof child === "string" && child.length > 0) {
        out[key] = `[REDACTED ${child.length} chars]`;
      } else {
        out[key] = redact(child, [...path, key]);
      }
    }
    return out;
  };
  return redact(config) as JsonObject;
}

async function getConfig(apiBase: string, token: string, pluginKey: string): Promise<PluginConfigRecord | null> {
  const result = await paperclipFetch(apiBase, token, `/api/plugins/${encodeURIComponent(pluginKey)}/config`);
  return result && typeof result === "object" && !Array.isArray(result) ? result as unknown as PluginConfigRecord : null;
}

async function restoreConfig(apiBase: string, token: string, pluginKey: string, config: JsonObject | null): Promise<boolean> {
  if (!config) return false;
  await paperclipFetch(apiBase, token, `/api/plugins/${encodeURIComponent(pluginKey)}/config`, {
    method: "POST",
    body: JSON.stringify({ configJson: config }),
  });
  return true;
}

async function install(apiBase: string, token: string, packageName: string, version?: string | null): Promise<JsonObject> {
  return compactPlugin(await paperclipFetch(apiBase, token, "/api/plugins/install", {
    method: "POST",
    body: JSON.stringify({ packageName, version: version?.trim() || undefined }),
  }));
}

async function remove(apiBase: string, token: string, pluginKey: string, purge: boolean): Promise<JsonObject> {
  const suffix = purge ? "?purge=true" : "";
  return compactPlugin(await paperclipFetch(apiBase, token, `/api/plugins/${encodeURIComponent(pluginKey)}${suffix}`, { method: "DELETE" }));
}

async function inspect(apiBase: string, token: string, pluginKey: string): Promise<JsonObject> {
  return compactPlugin(await paperclipFetch(apiBase, token, `/api/plugins/${encodeURIComponent(pluginKey)}`));
}

async function upgrade(apiBase: string, token: string, pluginKey: string, version?: string | null): Promise<JsonObject> {
  return compactPlugin(await paperclipFetch(apiBase, token, `/api/plugins/${encodeURIComponent(pluginKey)}/upgrade`, {
    method: "POST",
    body: JSON.stringify({ version: version?.trim() || undefined }),
  }));
}

export default function paperclipPluginManager(pi: ExtensionAPI) {
  pi.registerTool({
    name: "paperclip_plugin_manager",
    label: "Paperclip Plugin Manager",
    description: "Install, upgrade, replace, remove, inspect, and preserve config for Paperclip npm plugins. Useful when runtime npm plugin installs get cached/stale or capability upgrades require reinstall.",
    parameters: Type.Object({
      action: Type.Union([
        Type.Literal("install"),
        Type.Literal("upgrade"),
        Type.Literal("replace"),
        Type.Literal("remove"),
        Type.Literal("inspect"),
        Type.Literal("config"),
      ], { description: "Operation to run. replace = backup config, purge uninstall, install requested npm version, restore config." }),
      pluginKey: Type.Optional(Type.String({ description: "Plugin key/id, e.g. paperclip-slack-agent. Required for upgrade/replace/remove/inspect/config." })),
      packageName: Type.Optional(Type.String({ description: "NPM package name, e.g. @cartage/paperclip-plugin-slack-agent. Required for install and replace unless replace can inspect current packageName." })),
      version: Type.Optional(Type.String({ description: "NPM version to install/upgrade, e.g. 0.1.12. Passed separately, not as package@version." })),
      apiBase: Type.Optional(Type.String({ description: "Paperclip API base. Defaults to PAPERCLIP_API_BASE/PAPERCLIP_URL or the Cartage production instance." })),
      token: Type.Optional(Type.String({ description: "Board token. Prefer env/auth file; token is never returned." })),
      purge: Type.Optional(Type.Boolean({ description: "For remove/replace: hard-purge plugin state. Defaults true for replace, false for remove." })),
      preserveConfig: Type.Optional(Type.Boolean({ description: "For replace: backup and restore plugin config. Defaults true." })),
      showConfig: Type.Optional(Type.Boolean({ description: "For config action: include redacted config in output. Defaults false." })),
    }),
    async execute(_toolCallId, rawParams) {
      const params = rawParams as {
        action: PluginAction;
        pluginKey?: string;
        packageName?: string;
        version?: string;
        apiBase?: string;
        token?: string;
        purge?: boolean;
        preserveConfig?: boolean;
        showConfig?: boolean;
      };
      const apiBase = resolveApiBase(params);
      const token = resolveToken(apiBase, params);
      const steps: Json[] = [];

      const requirePluginKey = () => {
        if (!params.pluginKey?.trim()) throw new Error(`${params.action} requires pluginKey.`);
        return params.pluginKey.trim();
      };

      let result: Json;
      if (params.action === "install") {
        if (!params.packageName?.trim()) throw new Error("install requires packageName.");
        result = await install(apiBase, token, params.packageName.trim(), params.version);
      } else if (params.action === "upgrade") {
        result = await upgrade(apiBase, token, requirePluginKey(), params.version);
      } else if (params.action === "remove") {
        result = await remove(apiBase, token, requirePluginKey(), params.purge === true);
      } else if (params.action === "inspect") {
        result = await inspect(apiBase, token, requirePluginKey());
      } else if (params.action === "config") {
        const config = await getConfig(apiBase, token, requirePluginKey());
        result = {
          pluginKey: params.pluginKey,
          hasConfig: Boolean(config?.configJson),
          configKeys: config?.configJson ? Object.keys(config.configJson) : [],
          redactedConfig: params.showConfig ? redactConfig(config?.configJson ?? null) : undefined,
        };
      } else if (params.action === "replace") {
        const pluginKey = requirePluginKey();
        const before = await inspect(apiBase, token, pluginKey);
        const packageName = params.packageName?.trim() || (typeof before.packageName === "string" ? before.packageName : "");
        if (!packageName) throw new Error("replace requires packageName or an inspectable existing plugin with packageName.");

        const preserveConfig = params.preserveConfig !== false;
        const config = preserveConfig ? await getConfig(apiBase, token, pluginKey) : null;
        steps.push({ step: "inspect", plugin: before });
        steps.push({ step: "backup_config", preserved: Boolean(config?.configJson), configKeys: config?.configJson ? Object.keys(config.configJson) : [] });

        const removed = await remove(apiBase, token, pluginKey, params.purge !== false);
        steps.push({ step: "remove", plugin: removed });

        const installed = await install(apiBase, token, packageName, params.version);
        steps.push({ step: "install", plugin: installed });

        const installedPluginKey = typeof installed.pluginKey === "string" ? installed.pluginKey : pluginKey;
        const restored = await restoreConfig(apiBase, token, installedPluginKey, config?.configJson ?? null);
        steps.push({ step: "restore_config", restored });

        result = { action: "replace", apiBase, requested: { pluginKey, packageName, version: params.version ?? null }, steps, final: await inspect(apiBase, token, installedPluginKey) };
      } else {
        throw new Error(`Unsupported action: ${params.action}`);
      }

      return {
        content: [{ type: "text", text: JSON.stringify({ apiBase, result }, null, 2) }],
        details: { apiBase, result },
      };
    },
  });
}
