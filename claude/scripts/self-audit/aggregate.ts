// self-audit/aggregate.ts — Stage-1 rollups over the raw section data.
// Lane-state summary (wedged/zombie detection) + the session aggregate
// (turn distribution, leaderboards, token totals, adoption gaps, hygiene flag).

function percentile(sorted: number[], p: number): number {
  if (!sorted.length) return 0;
  const idx = Math.min(sorted.length - 1, Math.floor((p / 100) * sorted.length));
  return sorted[idx];
}

// Levenshtein distance → similarity in [0,1], used to fuzzy-match opener themes
// against existing command names when hunting adoption gaps.
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

// Lane-state rollup — counts across worktree lanes so the synth can flag wedged
// state machines and zombie panes without walking every row.
export function buildLaneStateSummary(rows: any[]) {
  const laneRows = rows.filter((r) => r.lane);
  return {
    laneCount: laneRows.length,
    running: laneRows.filter((r) => r.lane.hasPid).length,
    wedged: laneRows.filter((r) => r.lane.wedged).length,
    verified: laneRows.filter((r) => r.lane.verifyOk).length,
    wedgedLanes: laneRows
      .filter((r) => r.lane.wedged)
      .map((r) => ({ repo: r.repo, branch: r.branch, state: r.lane.agentState, staleDays: r.lane.stateAgeDays }))
      .sort((a, b) => (b.staleDays || 0) - (a.staleDays || 0)),
    oversizedLaneFiles: laneRows.flatMap((r) =>
      r.lane.oversizedLaneFiles.map((f: any) => ({ repo: r.repo, branch: r.branch, ...f })),
    ),
  };
}

export function buildSessionAgg(sess: any, inv: any) {
  if (!sess.available) return { available: false };

  const turns = sess.sessions.map((s: any) => s.turnCount).sort((a: number, b: number) => a - b);
  const slashLeader: Record<string, number> = {};
  const toolLeader: Record<string, number> = {};
  let handoff = 0, clear = 0, warnFired = 0, warnHonored = 0, tokIn = 0, tokOut = 0, cacheR = 0, cacheC = 0;
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

  return {
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
    slashLeaderboard: Object.entries(slashLeader).sort((a, b) => b[1] - a[1]).slice(0, 10),
    toolLeaderboard: Object.entries(toolLeader).sort((a, b) => b[1] - a[1]).slice(0, 10),
    tokens: { input: tokIn, output: tokOut, cacheRead: cacheR, cacheCreate: cacheC },
    parseErrorRate: sess.parseErrorRate,
    themes,
    flags: { adoptionGaps: adoption, handoffVsClear: handoffClearFlag },
  };
}
