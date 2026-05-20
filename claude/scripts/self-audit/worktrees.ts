// self-audit/worktrees.ts — §2: enumerate worktrees across ~/Documents/code/,
// flag stale lanes, and probe per-lane .claude/ state (agent-state, pid, verify.ok,
// wedged detection, oversized lane files).

import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { HOME, NOW, FIVE_DAYS, sh, lineByteCount, ageDaysOf } from "./util";

const DAY_MS = 24 * 60 * 60 * 1000;

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

export function worktrees() {
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
          ageDays: ageMs === Infinity ? null : Math.floor(ageMs / DAY_MS),
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
