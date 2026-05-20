#!/usr/bin/env bun
// self-audit.ts — Stage 1 data collector for /self-audit.
// Orchestrates the section collectors (inventory, worktrees, sessions, filesystem),
// builds the rollups, and writes a JSON pack to ~/.claude/audits/. Renders no markdown.
// Each section lives in ./self-audit/<section>.ts; this file is just the wiring + write.

import { mkdirSync, writeFileSync, unlinkSync, symlinkSync } from "node:fs";
import { join } from "node:path";
import { HOME } from "./self-audit/util";
import { inventory } from "./self-audit/inventory";
import { worktrees } from "./self-audit/worktrees";
import { sessions } from "./self-audit/sessions";
import { filesystem } from "./self-audit/filesystem";
import { buildLaneStateSummary, buildSessionAgg } from "./self-audit/aggregate";

const NAME = process.argv[2] || process.env.USER || "user";

const inv = inventory();
const wt = worktrees();
const sess = sessions();
const fsLayout = filesystem(wt.rows.map((r: any) => r.branch));
const laneStateSummary = buildLaneStateSummary(wt.rows);
const sessionAgg = buildSessionAgg(sess, inv);

const out = {
  name: NAME,
  generatedAt: new Date().toISOString(),
  inventory: inv,
  worktrees: wt,
  laneStateSummary,
  filesystem: fsLayout,
  sessionAgg,
  openers: Array.from(new Set(sess.openers || [])),
};

const auditsDir = join(HOME, ".claude", "audits");
mkdirSync(auditsDir, { recursive: true });
const stamp = new Date().toISOString().replace(/[:.]/g, "-").replace(/Z$/, "");
const outPath = join(auditsDir, `self-audit-${NAME}-${stamp}.json`);
writeFileSync(outPath, JSON.stringify(out, null, 2));

// maintain a stable "latest" symlink for tooling
const latest = join(auditsDir, `self-audit-${NAME}-latest.json`);
try { unlinkSync(latest); } catch {}
try { symlinkSync(outPath, latest); } catch {}
console.log(outPath);
