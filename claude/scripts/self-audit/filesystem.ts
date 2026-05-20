// self-audit/filesystem.ts — §5: global ~/.claude/ state hygiene. Ticket-tree decay,
// handoff archive pressure, orphan plans, oversized scripts, transcript-disk growth.

import { existsSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { HOME, sh, lineByteCount, ageDaysOf, walkMd } from "./util";

const GB = 1024 * 1024 * 1024;

export function filesystem(branchNames: string[]) {
  const root = join(HOME, ".claude");

  // tickets/ — per-project counts; structural files (_template, _epic) excluded.
  const ticketsDir = join(root, "tickets");
  const ticketProjects: { project: string; count: number; oldestAgeDays: number | null; flag: boolean }[] = [];
  let ticketsTotal = 0;
  let ticketsOver30dNonEpic = 0;
  if (existsSync(ticketsDir)) {
    for (const ent of readdirSync(ticketsDir, { withFileTypes: true })) {
      if (!ent.isDirectory() || ent.name.startsWith(".")) continue; // skip templates, README, .git
      const realFiles = walkMd(join(ticketsDir, ent.name)).filter((f) => !f.split("/").pop()!.startsWith("_"));
      let oldest: number | null = null;
      for (const f of realFiles) {
        ticketsTotal++;
        const age = ageDaysOf(f);
        if (age === null) continue;
        if (oldest === null || age > oldest) oldest = age;
        if (age > 30) ticketsOver30dNonEpic++;
      }
      ticketProjects.push({ project: ent.name, count: realFiles.length, oldestAgeDays: oldest, flag: realFiles.length >= 20 });
    }
  }
  ticketProjects.sort((a, b) => b.count - a.count);

  // handoffs/ — archive pressure when entries linger past 30d.
  const handoffsDir = join(root, "handoffs");
  let handoffCount = 0;
  let handoffOldestAgeDays: number | null = null;
  let handoffsOver30d = 0;
  if (existsSync(handoffsDir)) {
    for (const f of readdirSync(handoffsDir).filter((f) => f.endsWith(".md"))) {
      handoffCount++;
      const age = ageDaysOf(join(handoffsDir, f));
      if (age === null) continue;
      if (handoffOldestAgeDays === null || age > handoffOldestAgeDays) handoffOldestAgeDays = age;
      if (age > 30) handoffsOver30d++;
    }
  }

  // plans/ — orphaned when no live branch slug matches the plan filename.
  const plansDir = join(root, "plans");
  const plans: { name: string; ageDays: number | null; orphan: boolean }[] = [];
  if (existsSync(plansDir)) {
    for (const f of readdirSync(plansDir).filter((f) => f.endsWith(".md"))) {
      const slug = f.replace(/\.md$/, "").toLowerCase();
      const matched = branchNames.some(
        (b) => b.toLowerCase().includes(slug) || slug.includes(b.toLowerCase().split("/").pop() || "\0"),
      );
      plans.push({ name: f, ageDays: ageDaysOf(join(plansDir, f)), orphan: !matched });
    }
  }

  // scripts/ — oversized (>500 line) scripts are refactor candidates.
  const scriptsDir = join(root, "scripts");
  let scriptFileCount = 0;
  let scriptTotalLines = 0;
  const oversizedScripts: { name: string; lines: number }[] = [];
  if (existsSync(scriptsDir)) {
    for (const ent of readdirSync(scriptsDir, { withFileTypes: true })) {
      if (ent.isDirectory()) continue;
      scriptFileCount++;
      const { lines } = lineByteCount(join(scriptsDir, ent.name));
      scriptTotalLines += lines;
      if (lines > 500) oversizedScripts.push({ name: ent.name, lines });
    }
  }

  // projects/ transcripts — disk-growth watch (>5GB = prune candidate).
  const projectsDir = join(root, "projects");
  let transcriptBytes = 0;
  if (existsSync(projectsDir)) {
    const kb = sh(`du -sk "${projectsDir}" 2>/dev/null`).split(/\s+/)[0];
    transcriptBytes = kb ? parseInt(kb, 10) * 1024 : 0;
  }

  return {
    tickets: { total: ticketsTotal, over30dNonEpic: ticketsOver30dNonEpic, projects: ticketProjects },
    handoffs: { count: handoffCount, oldestAgeDays: handoffOldestAgeDays, over30d: handoffsOver30d },
    plans: { count: plans.length, orphanCount: plans.filter((p) => p.orphan).length, entries: plans },
    scripts: { fileCount: scriptFileCount, totalLines: scriptTotalLines, oversized: oversizedScripts.sort((a, b) => b.lines - a.lines) },
    transcripts: { bytes: transcriptBytes, gb: +(transcriptBytes / GB).toFixed(2), flag: transcriptBytes > 5 * GB },
  };
}
