// self-audit/sessions.ts — §3: parse the last 7d of Claude Code transcripts.
// Per-session: turn count, slash-command + tool-call tallies, token usage,
// turn-cap warnings + obedience, task openers (first prompt + first-after-/clear).
//
// Schema notes (Claude Code transcripts, observed v2.1.x):
//  - JSONL under ~/.claude/projects/<encoded-cwd>/<session-id>.jsonl
//  - user.message.content: string (real prompt, or isMeta=true local-command/hook)
//    OR array of blocks (tool_result => not a turn; text/image => a turn)
//  - assistant.message.content: array of blocks (thinking/text/tool_use{name})
//  - assistant.message.usage: input_tokens, cache_creation_input_tokens,
//    cache_read_input_tokens, output_tokens
//  - slash commands surface as content "<command-name>/foo</command-name>"

import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { HOME, NOW, SEVEN_DAYS } from "./util";

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
    return content.map((b) => (typeof b === "string" ? b : b?.text || "")).join("\n");
  }
  return "";
}

function isToolResult(content: any): boolean {
  return Array.isArray(content) && content.some((b) => b?.type === "tool_result");
}

export function sessions() {
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
