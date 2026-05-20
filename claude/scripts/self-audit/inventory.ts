// self-audit/inventory.ts — §1: count + flag commands, skills, subagents, CLAUDE.md
// files. Flags: commands/skills/subagents >200 lines, CLAUDE.md >150 (lean-config target).

import { existsSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { HOME, lineByteCount } from "./util";

export function inventory() {
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
