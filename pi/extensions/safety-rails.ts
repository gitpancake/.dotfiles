import { existsSync, realpathSync, statSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, isAbsolute, resolve, sep } from "node:path";
import { execFileSync } from "node:child_process";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

const writeTools = new Set(["write", "edit"]);

export default function (pi: ExtensionAPI) {
  pi.on("tool_call", async (event, ctx) => {
    if (event.toolName === "bash") {
      const command = String((event.input as { command?: unknown }).command ?? "");
      if (isBlockedLinearCreate(command)) {
        return {
          block: true,
          reason:
            "Blocked direct linear-ticket.py create. Use local briefs under $TICKETS_DIR; /ship owns PR reference tickets.",
        };
      }
      return undefined;
    }

    if (event.toolName === "read") {
      const input = event.input as { path?: unknown; offset?: unknown; limit?: unknown };
      if (input.offset !== undefined || input.limit !== undefined) return undefined;

      const targetPath = absolutePath(ctx.cwd, String(input.path ?? ""));
      if (targetPath && isLargeTextFile(targetPath) && ctx.hasUI) {
        ctx.ui.notify(`Large read: ${targetPath}. Prefer search then offset/limit.`, "warning");
      }
      return undefined;
    }

    if (!writeTools.has(event.toolName)) return undefined;

    const targetPath = absolutePath(ctx.cwd, String((event.input as { path?: unknown }).path ?? ""));
    if (!targetPath) return undefined;

    const violation = worktreeWriteViolation(ctx.cwd, targetPath);
    if (!violation) return undefined;

    return { block: true, reason: violation };
  });
}

function isBlockedLinearCreate(command: string): boolean {
  if (command.includes("LINEAR_TICKET_CREATE_OK=1")) return false;
  return command.includes("linear-ticket.py") && /\bcreate\b/.test(command);
}

function absolutePath(cwd: string, pathValue: string): string | undefined {
  if (!pathValue) return undefined;
  const expanded = pathValue.startsWith("~/") ? `${homedir()}${pathValue.slice(1)}` : pathValue;
  const resolved = isAbsolute(expanded) ? expanded : resolve(cwd, expanded);
  return realpathIfExists(resolved);
}

function realpathIfExists(pathValue: string): string {
  try {
    return realpathSync(pathValue);
  } catch {
    return pathValue;
  }
}

function isLargeTextFile(pathValue: string): boolean {
  try {
    const stat = statSync(pathValue);
    if (!stat.isFile() || stat.size < 50_000) return false;
    const extension = pathValue.split(".").pop()?.toLowerCase() ?? "";
    return !new Set(["png", "jpg", "jpeg", "gif", "webp", "pdf", "zip", "gz", "tar", "sqlite", "db"]).has(extension);
  } catch {
    return false;
  }
}

function worktreeWriteViolation(cwd: string, targetPath: string): string | undefined {
  const git = gitInfo(cwd);
  if (!git || samePath(git.gitDir, git.gitCommonDir)) return undefined;

  const mainRoot = dirname(git.gitCommonDir);
  if (!isInside(targetPath, mainRoot)) return undefined;
  if (isInside(targetPath, git.topLevel)) return undefined;
  if (isInside(targetPath, resolve(homedir(), ".claude", "tickets"))) return undefined;

  return `Blocked cross-worktree write: ${targetPath} is outside current worktree ${git.topLevel}`;
}

function gitInfo(cwd: string): { topLevel: string; gitDir: string; gitCommonDir: string } | undefined {
  try {
    const output = execFileSync(
      "git",
      ["-C", cwd, "rev-parse", "--show-toplevel", "--git-dir", "--git-common-dir"],
      { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] },
    )
      .trim()
      .split("\n");

    const [topLevel, rawGitDir, rawCommonDir] = output;
    return {
      topLevel: realpathIfExists(topLevel),
      gitDir: realpathIfExists(resolveGitPath(topLevel, rawGitDir)),
      gitCommonDir: realpathIfExists(resolveGitPath(topLevel, rawCommonDir)),
    };
  } catch {
    return undefined;
  }
}

function resolveGitPath(topLevel: string, gitPath: string): string {
  return isAbsolute(gitPath) ? gitPath : resolve(topLevel, gitPath);
}

function samePath(left: string, right: string): boolean {
  return left === right;
}

function isInside(child: string, parent: string): boolean {
  const normalizedChild = realpathIfExists(child);
  const normalizedParent = realpathIfExists(parent);
  return normalizedChild === normalizedParent || normalizedChild.startsWith(`${normalizedParent}${sep}`);
}
