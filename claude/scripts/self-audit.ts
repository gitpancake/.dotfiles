#!/usr/bin/env bun
// self-audit.ts — Stage 1 data collector for /self-audit.
// Does §1 inventory, §2 worktree state, §3 session shape (last 7d).
// Writes a JSON intermediate to /tmp/self-audit-<name>.json. Renders no markdown.
//
// Schema notes (Claude Code transcripts, observed v2.1.x):
//  - JSONL under ~/.claude/projects/<encoded-cwd>/<session-id>.jsonl
//  - line types: file-history-snapshot, attachment, user, assistant, system,
//    last-prompt, ai-title, queue-operation, pr-link
//  - user.message.content: string (real prompt, or isMeta=true local-command/hook)
//    OR array of blocks (tool_result => not a turn; text/image => a turn)
//  - assistant.message.content: array of blocks (thinking/text/tool_use{name})
//  - assistant.message.usage: input_tokens, cache_creation_input_tokens,
//    cache_read_input_tokens, output_tokens
//  - slash commands surface as content "<command-name>/foo</command-name>"

import { execSync } from "node:child_process";
import { readdirSync, readFileSync, statSync, existsSync } from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";

const HOME = homedir();
const NAME = process.argv[2] || process.env.USER || "user";
const NOW = Date.now();
const SEVEN_DAYS = 7 * 24 * 60 * 60 * 1000;
const FIVE_DAYS = 5 * 24 * 60 * 60 * 1000;

function sh(cmd: string): string {
  try {
    return execSync(cmd, { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).trim();
  } catch {
    return "";
  }
}

function lineByteCount(path: string): { lines: number; bytes: number } {
  try {
    const buf = readFileSync(path);
    const text = buf.toString("utf8");
    return { lines: text.split("\n").length, bytes: buf.length };
  } catch {
    return { lines: 0, bytes: 0 };
  }
}

function ageDaysOf(path: string): number | null {
  try {
    return Math.floor((NOW - statSync(path).mtimeMs) / (24 * 60 * 60 * 1000));
  } catch {
    return null;
  }
}

function walkMd(dir: string): string[] {
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

// Per-lane .claude/ state probe. Only meaningful for worktree lanes (paths under
// .claude/worktrees/) — NOT the repo-main checkout, whose .claude/ is the live config.
// agent-state vocab (wt-lanes): IDLE = parked/done, RUNNING / WAITING:* = active.
// Wedged = lane claims an active state but its state file is stale: the orchestrator
// died or the pane was killed mid-run, leaving a zombie state machine.
const LANE_STALE_DAYS = 2;
function laneState(wtPath: string) {
  const cdir = join(wtPath, ".claude");
  if (!existsSync(cdir)) return null;
  const stateFile = join(cdir, "agent-state");
  const agentState = existsSync(stateFile) ? readFileSync(stateFile, "utf8").trim() : null;
  const stateAgeDays = ageDaysOf(stateFile);
  const hasPid = existsSync(join(cdir, "agent-pid"));
  const verifyOk = existsSync(join(cdir, "verify.ok"));
  const isActiveState = !!agentState && agentState !== "IDLE";
  const wedged = isActiveState && stateAgeDays !== null && stateAgeDays > LANE_STALE_DAYS;

  // Oversized lane-owned files: regular files (not symlinks into shared config) in
  // .claude/ over 500 lines — e.g. a bloated progress.txt / prd.json / summary.
  const oversizedLaneFiles: { name: string; lines: number }[] = [];
  try {
    for (const ent of readdirSync(cdir, { withFileTypes: true })) {
      if (!ent.isFile() || ent.isSymbolicLink()) continue;
      const { lines } = lineByteCount(join(cdir, ent.name));
      if (lines > 500) oversizedLaneFiles.push({ name: ent.name, lines });
    }
  } catch {}

  return { agentState, stateAgeDays, hasPid, verifyOk, wedged, oversizedLaneFiles };
}

// ---------- §1 Inventory ----------
function inventory() {
  const commands: any[] = [];
  const cmdDir = join(HOME, ".claude", "commands");
  if (existsSync(cmdDir)) {
    for (const f of readdirSync(cmdDir).filter((f) => f.endsWith(".md"))) {
      const { lines, bytes } = lineByteCount(join(cmdDir, f));
      commands.push({ name: f.replace(/\.md$/, ""), path: join(cmdDir, f), lines, bytes, flag: lines > 200 });
    }
  }
  // project-local commands under ~/Documents/code/
  const codeRoot = join(HOME, "Documents", "code");
  if (existsSync(codeRoot)) {
    for (const repo of readdirSync(codeRoot)) {
      const pcDir = join(codeRoot, repo, ".claude", "commands");
      if (existsSync(pcDir)) {
        try {
          for (const f of readdirSync(pcDir).filter((f) => f.endsWith(".md"))) {
            const { lines, bytes } = lineByteCount(join(pcDir, f));
            commands.push({ name: `${repo}:${f.replace(/\.md$/, "")}`, path: join(pcDir, f), lines, bytes, flag: lines > 200 });
          }
        } catch {}
      }
    }
  }

  const skills: any[] = [];
  const skillDir = join(HOME, ".claude", "skills");
  if (existsSync(skillDir)) {
    for (const d of readdirSync(skillDir)) {
      const sp = join(skillDir, d, "SKILL.md");
      if (existsSync(sp)) {
        const { lines, bytes } = lineByteCount(sp);
        skills.push({ name: d, path: sp, lines, bytes, flag: lines > 200 });
      }
    }
  }

  const subagents: any[] = [];
  const agentDir = join(HOME, ".claude", "agents");
  if (existsSync(agentDir)) {
    for (const f of readdirSync(agentDir).filter((f) => f.endsWith(".md"))) {
      const { lines, bytes } = lineByteCount(join(agentDir, f));
      subagents.push({ name: f.replace(/\.md$/, ""), path: join(agentDir, f), lines, bytes, flag: lines > 200 });
    }
  }

  const claudeMds: any[] = [];
  const globalMd = join(HOME, ".claude", "CLAUDE.md");
  if (existsSync(globalMd)) {
    const { lines, bytes } = lineByteCount(globalMd);
    claudeMds.push({ name: "~/.claude/CLAUDE.md", path: globalMd, lines, bytes, flag: lines > 150 });
  }
  if (existsSync(codeRoot)) {
    for (const repo of readdirSync(codeRoot)) {
      const mp = join(codeRoot, repo, "CLAUDE.md");
      if (existsSync(mp)) {
        const { lines, bytes } = lineByteCount(mp);
        claudeMds.push({ name: `${repo}/CLAUDE.md`, path: mp, lines, bytes, flag: lines > 150 });
      }
    }
  }

  return { commands, skills, subagents, claudeMds };
}

// ---------- §2 Worktree state ----------
function defaultBranchFor(repoPath: string): string {
  // origin/HEAD is authoritative when set
  const sym = sh(`git -C "${repoPath}" symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null`);
  if (sym) return sym.replace(/^origin\//, "");
  // fallback: gh
  const ghDef = sh(`gh repo view --json defaultBranchRef -q .defaultBranchRef.name 2>/dev/null`);
  if (ghDef) return ghDef;
  // last resort: probe main/master locally
  if (sh(`git -C "${repoPath}" rev-parse --verify --quiet main`)) return "main";
  if (sh(`git -C "${repoPath}" rev-parse --verify --quiet master`)) return "master";
  return "main";
}

function worktrees() {
  const codeRoot = join(HOME, "Documents", "code");
  const hasGh = sh("command -v gh") !== "";
  const rows: any[] = [];
  if (!existsSync(codeRoot)) return { rows, hasGh };
  for (const repo of readdirSync(codeRoot)) {
    const repoPath = join(codeRoot, repo);
    if (!existsSync(join(repoPath, ".git"))) continue;
    const porcelain = sh(`git -C "${repoPath}" worktree list --porcelain`);
    if (!porcelain) continue;
    const defaultBranch = defaultBranchFor(repoPath);
    // parse blocks separated by blank lines
    let cur: any = {};
    const flush = () => {
      if (cur.worktree) {
        const wtPath = cur.worktree;
        const branch = (cur.branch || "").replace("refs/heads/", "") || "(detached)";
        const ctRaw = sh(`git -C "${wtPath}" log -1 --format=%ct HEAD`);
        const ct = ctRaw ? parseInt(ctRaw, 10) * 1000 : 0;
        const ageMs = ct ? NOW - ct : Infinity;
        let pr = "—";
        let prOpen = false;
        if (hasGh && branch !== "(detached)") {
          const prJson = sh(`gh pr list --head "${branch}" --json number,state,url 2>/dev/null`);
          if (prJson) {
            try {
              const arr = JSON.parse(prJson);
              if (arr.length) {
                pr = `#${arr[0].number} ${arr[0].state}`;
                prOpen = arr[0].state === "OPEN";
              }
            } catch {}
          }
        }
        // Stale = no commits in 5+d AND no open PR AND not the repo's default branch.
        // Bare entries excluded; detached HEADs cannot match a branch name → treated as non-default.
        const isDefault = branch === defaultBranch;
        const stale = ageMs > FIVE_DAYS && !prOpen && !cur.bare && !isDefault;
        // Lane state only for worktree lanes, not the repo-main checkout.
        const isLane = wtPath.includes("/.claude/worktrees/");
        rows.push({
          repo,
          path: wtPath,
          branch,
          defaultBranch,
          ageDays: ageMs === Infinity ? null : Math.floor(ageMs / (24 * 60 * 60 * 1000)),
          pr,
          prOpen,
          stale,
          isMain: wtPath === repoPath,
          isDefault,
          lane: isLane ? laneState(wtPath) : null,
        });
      }
      cur = {};
    };
    for (const line of porcelain.split("\n")) {
      if (line.trim() === "") {
        flush();
        continue;
      }
      const [key, ...rest] = line.split(" ");
      const val = rest.join(" ");
      if (key === "worktree") cur.worktree = val;
      else if (key === "branch") cur.branch = val;
      else if (key === "bare") cur.bare = true;
      else if (key === "detached") cur.detached = true;
    }
    flush();
  }
  return { rows, hasGh };
}

// ---------- §3 Session shape (last 7d) ----------
// turn-cap-warn.sh fires these via a UserPromptSubmit hook; they land in the
// transcript as attachment entries with attachment.type === "hook_system_message".
// Match the emitted warning text, NOT the protocol doc (which trips every tier).
const TURN_CAP_TIERS = [
  { tier: "Turn 30", re: /TURN 30/ },
  { tier: "Turn 50", re: /TURN 50/ },
  { tier: "Turn 75", re: /TURN 75/ },
  { tier: "Turn 100+", re: /SESSION OVERRUN/ },
];

function extractText(content: any): string {
  if (content == null) return "";
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    return content
      .map((b) => (typeof b === "string" ? b : b?.text || ""))
      .join("\n");
  }
  return "";
}

function isToolResult(content: any): boolean {
  return Array.isArray(content) && content.some((b) => b?.type === "tool_result");
}

function sessions() {
  const projectsRoot = join(HOME, ".claude", "projects");
  if (!existsSync(projectsRoot)) return { available: false, sessions: [], openers: [] };

  const sessionStats: any[] = [];
  const openers: string[] = [];
  let parseErrors = 0;
  let totalLines = 0;

  for (const proj of readdirSync(projectsRoot)) {
    const projDir = join(projectsRoot, proj);
    let files: string[];
    try {
      files = readdirSync(projDir).filter((f) => f.endsWith(".jsonl"));
    } catch {
      continue;
    }
    for (const file of files) {
      const fpath = join(projDir, file);
      let st;
      try {
        st = statSync(fpath);
      } catch {
        continue;
      }
      if (NOW - st.mtimeMs > SEVEN_DAYS) continue;

      let raw: string;
      try {
        raw = readFileSync(fpath, "utf8");
      } catch {
        continue;
      }

      let turnCount = 0;
      const slashCmds: Record<string, number> = {};
      const toolCalls: Record<string, number> = {};
      let tokensIn = 0,
        tokensOut = 0,
        cacheRead = 0,
        cacheCreate = 0;
      const warnings: { turn: number; tier: string }[] = [];
      const hygieneTurns: { turn: number; cmd: string }[] = [];
      let prevWasClear = false;
      let sawFirstOpener = false;

      for (const line of raw.split("\n")) {
        if (!line.trim()) continue;
        totalLines++;
        let o: any;
        try {
          o = JSON.parse(line);
        } catch {
          parseErrors++;
          continue;
        }
        const type = o.type;

        // turn-cap warnings land as hook_system_message attachments
        if (type === "attachment" && o.attachment?.type === "hook_system_message") {
          const content = o.attachment.content || "";
          for (const t of TURN_CAP_TIERS) {
            if (t.re.test(content)) {
              warnings.push({ turn: turnCount, tier: t.tier });
              break;
            }
          }
        }

        if (type === "user") {
          const content = o.message?.content;
          if (isToolResult(content)) continue; // tool result, not a turn
          const text = extractText(content);

          // slash command detection (both inline /foo and <command-name> form)
          const cmdTag = text.match(/<command-name>\s*\/?([a-z][a-z0-9:-]*)\s*<\/command-name>/i);
          const cmdInline = text.match(/^\s*\/([a-z][a-z0-9:-]*)/);
          const cmd = cmdTag ? cmdTag[1] : cmdInline ? cmdInline[1] : null;
          if (cmd) {
            slashCmds[cmd] = (slashCmds[cmd] || 0) + 1;
            if (cmd === "handoff" || cmd === "clear") {
              hygieneTurns.push({ turn: turnCount, cmd });
            }
            if (cmd === "clear") prevWasClear = true;
          }

          // meta messages (local-command wrappers, hooks) are not turns
          if (o.isMeta) continue;

          // a real turn
          turnCount++;

          // task opener: first real prompt, or first after a /clear
          const trimmed = text.trim();
          const isCommandLike = /^<command-name>/.test(trimmed) || /^<local-command/.test(trimmed);
          if (!isCommandLike && trimmed) {
            if (!sawFirstOpener || prevWasClear) {
              openers.push(trimmed.slice(0, 200));
              sawFirstOpener = true;
              prevWasClear = false;
            }
          }
        }

        if (type === "assistant") {
          const msg = o.message || {};
          const u = msg.usage || {};
          tokensIn += u.input_tokens || 0;
          tokensOut += u.output_tokens || 0;
          cacheRead += u.cache_read_input_tokens || 0;
          cacheCreate += u.cache_creation_input_tokens || 0;
          const blocks = Array.isArray(msg.content) ? msg.content : [];
          for (const b of blocks) {
            if (b?.type === "tool_use" && b.name) {
              toolCalls[b.name] = (toolCalls[b.name] || 0) + 1;
            }
          }
        }
      }

      // turn-cap obedience: was a /handoff or /clear within 5 turns of each warning?
      let honored = 0;
      for (const w of warnings) {
        if (hygieneTurns.some((h) => h.turn >= w.turn && h.turn <= w.turn + 5)) honored++;
      }

      sessionStats.push({
        file,
        project: proj,
        mtime: st.mtimeMs,
        turnCount,
        slashCmds,
        toolCalls,
        tokensIn,
        tokensOut,
        cacheRead,
        cacheCreate,
        warningsFired: warnings.length,
        warningsHonored: honored,
        handoffCount: Object.entries(slashCmds).filter(([k]) => k === "handoff").reduce((a, [, v]) => a + v, 0),
        clearCount: Object.entries(slashCmds).filter(([k]) => k === "clear").reduce((a, [, v]) => a + v, 0),
      });
    }
  }

  return {
    available: true,
    sessions: sessionStats,
    openers,
    parseErrors,
    totalLines,
    parseErrorRate: totalLines ? parseErrors / totalLines : 0,
  };
}

// ---------- §5 Filesystem layout ----------
// Global ~/.claude/ state hygiene: ticket-tree decay, handoff archive pressure,
// orphan plans, oversized scripts, transcript-disk growth. Closes the §5 half the
// command spec deferred to "inline parse" — now emitted structurally.
function filesystem(branchNames: string[]) {
  const root = join(HOME, ".claude");

  // tickets/ — per-project counts; structural files (_template, _epic) excluded.
  const ticketsDir = join(root, "tickets");
  const ticketProjects: { project: string; count: number; oldestAgeDays: number | null; flag: boolean }[] = [];
  let ticketsTotal = 0;
  let ticketsOver30dNonEpic = 0;
  if (existsSync(ticketsDir)) {
    for (const ent of readdirSync(ticketsDir, { withFileTypes: true })) {
      if (!ent.isDirectory() || ent.name.startsWith(".")) continue; // skip templates, README, .git
      const realFiles = walkMd(join(ticketsDir, ent.name)).filter(
        (f) => !f.split("/").pop()!.startsWith("_"),
      );
      let oldest: number | null = null;
      for (const f of realFiles) {
        ticketsTotal++;
        const age = ageDaysOf(f);
        if (age === null) continue;
        if (oldest === null || age > oldest) oldest = age;
        if (age > 30) ticketsOver30dNonEpic++;
      }
      ticketProjects.push({
        project: ent.name,
        count: realFiles.length,
        oldestAgeDays: oldest,
        flag: realFiles.length >= 20,
      });
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
  const GB = 1024 * 1024 * 1024;

  return {
    tickets: { total: ticketsTotal, over30dNonEpic: ticketsOver30dNonEpic, projects: ticketProjects },
    handoffs: { count: handoffCount, oldestAgeDays: handoffOldestAgeDays, over30d: handoffsOver30d },
    plans: { count: plans.length, orphanCount: plans.filter((p) => p.orphan).length, entries: plans },
    scripts: {
      fileCount: scriptFileCount,
      totalLines: scriptTotalLines,
      oversized: oversizedScripts.sort((a, b) => b.lines - a.lines),
    },
    transcripts: {
      bytes: transcriptBytes,
      gb: +(transcriptBytes / GB).toFixed(2),
      flag: transcriptBytes > 5 * GB,
    },
  };
}

// ---------- Aggregate + write ----------
function percentile(sorted: number[], p: number): number {
  if (!sorted.length) return 0;
  const idx = Math.min(sorted.length - 1, Math.floor((p / 100) * sorted.length));
  return sorted[idx];
}

// Levenshtein-based similarity in [0,1]
function lev(a: string, b: string): number {
  if (a === b) return 0;
  if (!a.length) return b.length;
  if (!b.length) return a.length;
  const dp = Array.from({ length: a.length + 1 }, () => new Array(b.length + 1).fill(0));
  for (let i = 0; i <= a.length; i++) dp[i][0] = i;
  for (let j = 0; j <= b.length; j++) dp[0][j] = j;
  for (let i = 1; i <= a.length; i++) {
    for (let j = 1; j <= b.length; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      dp[i][j] = Math.min(dp[i - 1][j] + 1, dp[i][j - 1] + 1, dp[i - 1][j - 1] + cost);
    }
  }
  return dp[a.length][b.length];
}
function sim(a: string, b: string): number {
  const m = Math.max(a.length, b.length);
  return m === 0 ? 1 : 1 - lev(a, b) / m;
}

const STOP = new Set([
  "the","a","an","please","can","we","i","to","for","of","and","or","is","it","this","that",
  "with","in","on","at","by","be","will","do","did","done","my","our","you","your","let","make",
  "have","has","had","not","but","so","just","need","want","also","then","there","here","up",
  "out","into","from","about","as","if","really","quick","help","try","get","go","using","use",
  "what","why","how","when","where","who","which","whose","yes","no","ok","okay","sure","thanks",
  "look","see","check","tell","show","find","read","run","add","new","old","more","less","like",
  "chars","char","line","lines","file","files",
]);

function themesFromOpeners(openers: string[]): { theme: string; count: number }[] {
  const counts: Record<string, number> = {};
  for (const o of openers) {
    const tokens = o
      .toLowerCase()
      .replace(/[`*_\[\]()<>"']/g, " ")
      .split(/[^a-z0-9-]+/)
      .filter((t) => t && t.length >= 3 && !STOP.has(t) && !/^\d+$/.test(t));
    // dedup per opener so a chatty prompt doesn't dominate
    for (const t of Array.from(new Set(tokens))) counts[t] = (counts[t] || 0) + 1;
  }
  return Object.entries(counts)
    .filter(([, c]) => c >= 2)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 15)
    .map(([theme, count]) => ({ theme, count }));
}

function adoptionGaps(
  themes: { theme: string; count: number }[],
  commandNames: string[],
  slashLeader: Record<string, number>,
) {
  const gaps: any[] = [];
  for (const { theme, count } of themes) {
    let best = { name: "", score: 0 };
    for (const c of commandNames) {
      // strip "<repo>:" project-local prefix for matching
      const bare = c.includes(":") ? c.split(":").pop()! : c;
      const sub = bare.includes(theme) || theme.includes(bare);
      const s = sub ? Math.max(0.85, sim(theme, bare)) : sim(theme, bare);
      if (s > best.score) best = { name: c, score: s };
    }
    if (best.score < 0.6) continue; // no plausible command for this theme
    const invocations = slashLeader[best.name.includes(":") ? best.name.split(":").pop()! : best.name] || 0;
    const gap = count - invocations;
    if (gap > 0) gaps.push({ theme, themeCount: count, command: best.name, similarity: +best.score.toFixed(2), invocations, gap });
  }
  return gaps.sort((a, b) => b.gap - a.gap);
}

const inv = inventory();
const wt = worktrees();
const sess = sessions();
const fsLayout = filesystem(wt.rows.map((r: any) => r.branch));

// Lane-state rollup — counts across worktree lanes so the synth can flag wedged
// state machines and zombie panes without walking every row.
const laneRows = wt.rows.filter((r: any) => r.lane);
const laneStateSummary = {
  laneCount: laneRows.length,
  running: laneRows.filter((r: any) => r.lane.hasPid).length,
  wedged: laneRows.filter((r: any) => r.lane.wedged).length,
  verified: laneRows.filter((r: any) => r.lane.verifyOk).length,
  wedgedLanes: laneRows
    .filter((r: any) => r.lane.wedged)
    .map((r: any) => ({ repo: r.repo, branch: r.branch, state: r.lane.agentState, staleDays: r.lane.stateAgeDays }))
    .sort((a: any, b: any) => (b.staleDays || 0) - (a.staleDays || 0)),
  oversizedLaneFiles: laneRows.flatMap((r: any) =>
    r.lane.oversizedLaneFiles.map((f: any) => ({ repo: r.repo, branch: r.branch, ...f })),
  ),
};

let agg: any = { available: sess.available };
if (sess.available) {
  const turns = sess.sessions.map((s: any) => s.turnCount).sort((a: number, b: number) => a - b);
  const slashLeader: Record<string, number> = {};
  const toolLeader: Record<string, number> = {};
  let handoff = 0,
    clear = 0,
    warnFired = 0,
    warnHonored = 0,
    tokIn = 0,
    tokOut = 0,
    cacheR = 0,
    cacheC = 0;
  for (const s of sess.sessions) {
    for (const [k, v] of Object.entries(s.slashCmds)) slashLeader[k] = (slashLeader[k] || 0) + (v as number);
    for (const [k, v] of Object.entries(s.toolCalls)) toolLeader[k] = (toolLeader[k] || 0) + (v as number);
    handoff += s.handoffCount;
    clear += s.clearCount;
    warnFired += s.warningsFired;
    warnHonored += s.warningsHonored;
    tokIn += s.tokensIn;
    tokOut += s.tokensOut;
    cacheR += s.cacheRead;
    cacheC += s.cacheCreate;
  }
  const themes = themesFromOpeners(sess.openers || []);
  const commandNames = inv.commands.map((c: any) => c.name);
  const adoption = adoptionGaps(themes, commandNames, slashLeader);

  // Explicit /handoff vs /clear split flag.
  // Healthy hygiene = handoff used roughly as often as clear (prefer handoff).
  // Skew toward clear means context is being dumped without capturing state.
  const totalHygiene = handoff + clear;
  const handoffShare = totalHygiene ? handoff / totalHygiene : null;
  const handoffClearFlag = {
    handoff,
    clear,
    handoffShare,
    flagged: totalHygiene >= 3 && handoffShare !== null && handoffShare < 0.5,
    note:
      totalHygiene < 3
        ? "insufficient hygiene events to judge"
        : handoffShare !== null && handoffShare < 0.5
          ? "/clear dominates — state being dumped without /handoff capture"
          : "balanced",
  };

  agg = {
    available: true,
    sessionCount: sess.sessions.length,
    turnDistribution: {
      p50: percentile(turns, 50),
      p75: percentile(turns, 75),
      p95: percentile(turns, 95),
      max: turns.length ? turns[turns.length - 1] : 0,
    },
    handoffCount: handoff,
    clearCount: clear,
    warningsFired: warnFired,
    warningsHonored: warnHonored,
    obedienceRatio: warnFired ? warnHonored / warnFired : null,
    slashLeaderboard: Object.entries(slashLeader)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 10),
    toolLeaderboard: Object.entries(toolLeader)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 10),
    tokens: { input: tokIn, output: tokOut, cacheRead: cacheR, cacheCreate: cacheC },
    parseErrorRate: sess.parseErrorRate,
    themes,
    flags: {
      adoptionGaps: adoption,
      handoffVsClear: handoffClearFlag,
    },
  };
}

// dedup openers
const openerSet = Array.from(new Set(sess.openers || []));

const out = {
  name: NAME,
  generatedAt: new Date().toISOString(),
  inventory: inv,
  worktrees: wt,
  laneStateSummary,
  filesystem: fsLayout,
  sessionAgg: agg,
  openers: openerSet,
};

const fs = require("node:fs");
const auditsDir = join(HOME, ".claude", "audits");
fs.mkdirSync(auditsDir, { recursive: true });
const stamp = new Date().toISOString().replace(/[:.]/g, "-").replace(/Z$/, "");
const outPath = join(auditsDir, `self-audit-${NAME}-${stamp}.json`);
fs.writeFileSync(outPath, JSON.stringify(out, null, 2));
// also maintain a stable "latest" symlink for tooling
const latest = join(auditsDir, `self-audit-${NAME}-latest.json`);
try { fs.unlinkSync(latest); } catch {}
try { fs.symlinkSync(outPath, latest); } catch {}
console.log(outPath);
