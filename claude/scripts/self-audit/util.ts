// self-audit/util.ts — shared constants + fs/time helpers for the collector.
// NOW is captured once at import so every section measures against the same instant.

import { execSync } from "node:child_process";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";

export const HOME = homedir();
export const NOW = Date.now();
export const SEVEN_DAYS = 7 * 24 * 60 * 60 * 1000;
export const FIVE_DAYS = 5 * 24 * 60 * 60 * 1000;
const DAY_MS = 24 * 60 * 60 * 1000;

// Run a shell command, swallow failures to "" so a missing binary never aborts a scan.
export function sh(cmd: string): string {
  try {
    return execSync(cmd, { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).trim();
  } catch {
    return "";
  }
}

export function lineByteCount(path: string): { lines: number; bytes: number } {
  try {
    const buf = readFileSync(path);
    return { lines: buf.toString("utf8").split("\n").length, bytes: buf.length };
  } catch {
    return { lines: 0, bytes: 0 };
  }
}

export function ageDaysOf(path: string): number | null {
  try {
    return Math.floor((NOW - statSync(path).mtimeMs) / DAY_MS);
  } catch {
    return null;
  }
}

export function walkMd(dir: string): string[] {
  const out: string[] = [];
  let ents;
  try {
    ents = readdirSync(dir, { withFileTypes: true });
  } catch {
    return out;
  }
  for (const ent of ents) {
    const p = join(dir, ent.name);
    if (ent.isDirectory()) out.push(...walkMd(p));
    else if (ent.isFile() && ent.name.endsWith(".md")) out.push(p);
  }
  return out;
}
