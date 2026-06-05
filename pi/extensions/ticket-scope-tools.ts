import { execSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { basename, dirname, join } from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

type ScopeTicketParams = {
  action?: "inspect" | "write";
  area?: string;
  slug?: string;
  content?: string;
};

const DEFAULT_AREAS = ["integrations", "platform", "ops", "tooling", "spikes"];

function gitProjectBase(): string | null {
  try {
    const root = execSync("git rev-parse --show-toplevel", {
      stdio: ["ignore", "pipe", "ignore"],
    })
      .toString()
      .trim();
    return root ? basename(root) : null;
  } catch {
    return null;
  }
}

// Pi tickets are harness-scoped to ~/.pi/tickets/<project>, independent of
// Claude's $TICKETS_DIR (which points at ~/.claude/tickets/<project>).
function projectDir(): string {
  if (process.env.PI_TICKETS_DIR) return process.env.PI_TICKETS_DIR;
  const treeRoot = join(homedir(), ".pi", "tickets");
  const base = gitProjectBase();
  return base ? join(treeRoot, base) : treeRoot;
}

// Templates and the README contract live at the tree root, one level above the
// per-project ticket folder.
function treeRoot(): string {
  return dirname(projectDir());
}

function readIfExists(path: string): string | null {
  return existsSync(path) ? readFileSync(path, "utf8") : null;
}

function validateSlug(slug: string): string {
  if (!/^[a-z0-9][a-z0-9-]{1,80}$/.test(slug)) {
    throw new Error(
      "Slug must be kebab-case, descriptive, and contain only lowercase letters, numbers, and hyphens.",
    );
  }
  return slug;
}

function validateArea(root: string, area: string): string {
  const allowed = DEFAULT_AREAS.filter((candidate) =>
    existsSync(join(root, candidate)),
  );
  const effectiveAllowed = allowed.length > 0 ? allowed : DEFAULT_AREAS;
  if (!effectiveAllowed.includes(area)) {
    throw new Error(`Area must be one of: ${effectiveAllowed.join(", ")}.`);
  }
  return area;
}

function inspectTicketContract() {
  const root = projectDir();
  const tree = treeRoot();
  return {
    ticketsDir: root,
    treeRoot: tree,
    areas: DEFAULT_AREAS.filter((area) => existsSync(join(root, area))),
    template: readIfExists(join(tree, "_TEMPLATE.md")),
    epicTemplate: readIfExists(join(tree, "_EPIC-TEMPLATE.md")),
    childTemplate: readIfExists(join(tree, "_CHILD-TEMPLATE.md")),
    contractSummary: [
      "Filename is a descriptive slug; never an ID.",
      "Single tickets live at <area>/<slug>.md.",
      "Use template frontmatter; status draft; external tracker fields blank unless known.",
      "Set created with a full UTC ISO instant.",
      "Do not author product code from /scope.",
    ],
  };
}

export default function ticketScopeTools(pi: ExtensionAPI) {
  pi.registerTool({
    name: "scope_ticket",
    label: "Scope Ticket",
    description:
      "Inspect the local ticket contract/templates or write an approved scoped ticket brief to the local ticket tree in one call.",
    promptSnippet: "Inspect/write local ticket briefs",
    promptGuidelines: [
      "Use scope_ticket action='inspect' at the start of /scope instead of manually reading README/template files.",
      "Use action='write' only after the user approves the rendered brief (e.g. says go).",
      "The tool validates area/slug, creates parent dirs, refuses to overwrite, and writes under the Pi ticket home (~/.pi/tickets/<project>).",
    ],
    parameters: Type.Object({
      action: Type.Optional(
        Type.Union([Type.Literal("inspect"), Type.Literal("write")], {
          description:
            "Inspect ticket contract/templates or write the approved ticket. Defaults to inspect.",
        }),
      ),
      area: Type.Optional(
        Type.String({
          description: "Ticket area for write, e.g. integrations.",
        }),
      ),
      slug: Type.Optional(
        Type.String({ description: "Kebab-case filename slug without .md." }),
      ),
      content: Type.Optional(
        Type.String({
          description: "Full approved markdown ticket content to write.",
        }),
      ),
    }),
    async execute(_toolCallId, params: ScopeTicketParams) {
      const action = params.action ?? "inspect";
      if (action === "inspect") {
        const result = inspectTicketContract();
        return {
          content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
          details: result,
        };
      }

      const root = projectDir();
      if (!params.area || !params.slug || !params.content) {
        throw new Error(
          "scope_ticket write requires area, slug, and full approved content.",
        );
      }
      const area = validateArea(root, params.area);
      const slug = validateSlug(params.slug);
      const target = join(root, area, `${slug}.md`);
      if (existsSync(target))
        throw new Error(`Refusing to overwrite existing ticket: ${target}`);
      mkdirSync(dirname(target), { recursive: true });
      writeFileSync(target, params.content, "utf8");
      const result = {
        path: target,
        slug,
        area,
        bytesWritten: Buffer.byteLength(params.content, "utf8"),
      };
      return {
        content: [{ type: "text", text: `Brief written: ${target}` }],
        details: result,
      };
    },
  });
}
