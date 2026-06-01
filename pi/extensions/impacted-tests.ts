import { execFileSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { basename, dirname, extname, join, relative, sep } from "node:path";
import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

type ImpactedTestsInput = {
  baseRef?: string;
  changedFiles?: string[];
};

type TestRunRecord = {
  changedKey: string;
  command: string;
  at: number;
};

const testRunsByRoot = new Map<string, TestRunRecord>();

export default function impactedTests(pi: ExtensionAPI) {
  pi.on("before_agent_start", async (event) => ({
    systemPrompt: `${event.systemPrompt}\n\n## Impacted test discipline\n\nWhen you change code in any git project:\n- Before pushing, creating a PR, or saying work is ready, identify tests impacted by the changed files.\n- Prefer the \`find_impacted_tests\` tool, or search manually with git diff + test filename/import references.\n- Run only the focused impacted tests first. Do not default to the whole suite unless focused tests cannot be identified or the project requires it.\n- If no impacted tests exist, state the search you performed and why no focused test applies.\n- Include the exact focused test command and result in your final update.\n`,
  }));

  pi.registerTool({
    name: "find_impacted_tests",
    label: "Find Impacted Tests",
    description:
      "Find likely tests impacted by current git changes and suggest focused test commands for the current project.",
    parameters: Type.Object({
      baseRef: Type.Optional(Type.String({ description: "Optional git ref to diff against, e.g. origin/main" })),
      changedFiles: Type.Optional(Type.Array(Type.String(), { description: "Optional changed files to analyze instead of git diff" })),
    }),
    async execute(_toolCallId, params: ImpactedTestsInput, _signal, _onUpdate, ctx) {
      const report = buildImpactedTestReport(ctx.cwd, params);
      return {
        content: [{ type: "text", text: formatReport(report) }],
        details: report,
      };
    },
  });

  pi.on("tool_result", async (event, ctx) => {
    if (event.toolName !== "bash") return undefined;
    if (event.isError) return undefined;

    const command = String((event.input as { command?: unknown }).command ?? "");
    if (!isTestCommand(command)) return undefined;

    const root = gitRoot(ctx.cwd);
    if (!root) return undefined;

    const changedFiles = currentChangedFiles(root);
    testRunsByRoot.set(root, {
      changedKey: changedFiles.sort().join("\n"),
      command,
      at: Date.now(),
    });
    return undefined;
  });

  pi.on("tool_call", async (event, ctx) => {
    if (event.toolName !== "bash") return undefined;

    const command = String((event.input as { command?: unknown }).command ?? "");
    if (!isPushOrPrCommand(command)) return undefined;
    if (/PI_SKIP_IMPACTED_TESTS=1/.test(command)) return undefined;

    const root = gitRoot(ctx.cwd);
    if (!root) return undefined;

    const changedFiles = currentChangedFiles(root);
    if (changedFiles.length === 0) return undefined;

    const changedKey = [...changedFiles].sort().join("\n");
    const priorRun = testRunsByRoot.get(root);
    if (priorRun?.changedKey === changedKey) return undefined;

    const report = buildImpactedTestReport(root, { changedFiles });
    const focused = report.suggestedCommands.length > 0 ? report.suggestedCommands.join("\n") : "No focused command inferred; explain the search, then run the nearest project-specific focused test command.";

    return {
      block: true,
      reason: [
        "Blocked push/PR until focused impacted tests are handled.",
        `Changed files: ${changedFiles.join(", ")}`,
        `Likely impacted tests: ${report.impactedTests.length > 0 ? report.impactedTests.join(", ") : "none found"}`,
        "Run focused impacted tests first, then retry. Suggested command(s):",
        focused,
        "Override only when appropriate with PI_SKIP_IMPACTED_TESTS=1 and explain why.",
      ].join("\n"),
    };
  });
}

function buildImpactedTestReport(cwd: string, input: ImpactedTestsInput) {
  const root = gitRoot(cwd) ?? cwd;
  const changedFiles = normalizeFiles(input.changedFiles ?? changedFilesForReport(root, input.baseRef));
  const trackedFiles = gitLines(root, ["ls-files"]);
  const testFiles = trackedFiles.filter(isTestFile);
  const impactedTests = findImpactedTests(changedFiles, testFiles, root);
  const suggestedCommands = suggestCommands(root, impactedTests);

  return {
    root,
    changedFiles,
    impactedTests,
    suggestedCommands,
    searched: [
      "changed files from git diff/status",
      "changed files that are tests",
      "sibling *.test/spec files",
      "__tests__/tests/test directories near changed files",
      "test files referencing changed basename or import stem",
    ],
  };
}

function formatReport(report: ReturnType<typeof buildImpactedTestReport>): string {
  return [
    `Git root: ${report.root}`,
    `Changed files (${report.changedFiles.length}):`,
    ...indent(report.changedFiles),
    `Likely impacted tests (${report.impactedTests.length}):`,
    ...(report.impactedTests.length > 0 ? indent(report.impactedTests) : ["  - none found"]),
    "Suggested focused command(s):",
    ...(report.suggestedCommands.length > 0 ? indent(report.suggestedCommands) : ["  - none inferred"]),
    "Search performed:",
    ...indent(report.searched),
  ].join("\n");
}

function indent(values: string[]): string[] {
  return values.map((value) => `  - ${value}`);
}

function gitRoot(cwd: string): string | undefined {
  try {
    return execFileSync("git", ["-C", cwd, "rev-parse", "--show-toplevel"], { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).trim();
  } catch {
    return undefined;
  }
}

function gitLines(cwd: string, args: string[]): string[] {
  try {
    return execFileSync("git", ["-C", cwd, ...args], { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] })
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean);
  } catch {
    return [];
  }
}

function changedFilesForReport(root: string, baseRef?: string): string[] {
  const files = new Set<string>();
  for (const file of currentChangedFiles(root)) files.add(file);

  const ref = baseRef ?? upstreamRef(root);
  if (ref) {
    for (const file of gitLines(root, ["diff", "--name-only", "--diff-filter=ACMR", `${ref}...HEAD`])) files.add(file);
  }

  return [...files];
}

function currentChangedFiles(root: string): string[] {
  const files = new Set<string>();
  for (const file of gitLines(root, ["diff", "--name-only", "--diff-filter=ACMR", "HEAD"])) files.add(file);
  for (const file of gitLines(root, ["diff", "--cached", "--name-only", "--diff-filter=ACMR"])) files.add(file);
  for (const status of gitLines(root, ["status", "--porcelain"])) {
    const file = status.slice(3).split(" -> ").pop()?.trim();
    if (file) files.add(file);
  }
  return normalizeFiles([...files]);
}

function upstreamRef(root: string): string | undefined {
  const ref = gitLines(root, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])[0];
  return ref && ref !== "@{u}" ? ref : undefined;
}

function normalizeFiles(files: string[]): string[] {
  return [...new Set(files.map((file) => file.replace(/^\.\//, "")).filter(Boolean))].sort();
}

function isTestFile(file: string): boolean {
  return /(^|\/)(__tests__|tests?|spec)\//i.test(file) || /(^|[._-])(test|spec)\.[cm]?[jt]sx?$/i.test(file) || /(^|[._-])(test|spec)\.(py|rb|go|rs)$/i.test(file);
}

function findImpactedTests(changedFiles: string[], testFiles: string[], root: string): string[] {
  const impacted = new Set<string>();
  const changedTests = changedFiles.filter(isTestFile);
  for (const file of changedTests) impacted.add(file);

  for (const changed of changedFiles.filter((file) => !isTestFile(file))) {
    const dir = dirname(changed);
    const stem = basename(changed, extname(changed));
    const compactStem = stem.replace(/\.(service|controller|component|hook|util|utils|types|model|schema)$/i, "");
    const nearbyDirs = ancestorDirs(dir).flatMap((ancestor) => [ancestor, join(ancestor, "test"), join(ancestor, "tests"), join(ancestor, "__tests__")]);

    for (const test of testFiles) {
      const testBase = basename(test);
      if (testBase.startsWith(`${stem}.`) || testBase.startsWith(`${compactStem}.`)) impacted.add(test);
      if (nearbyDirs.some((nearby) => sameOrInside(dirname(test), nearby)) && test.includes(compactStem)) impacted.add(test);
    }

    const importNeedles = [stem, compactStem, withoutExtension(changed), `../${withoutExtension(changed)}`, `./${stem}`].filter(Boolean);
    for (const test of testFiles) {
      if (impacted.has(test)) continue;
      const text = readSmallFile(join(root, test));
      if (!text) continue;
      if (importNeedles.some((needle) => text.includes(needle))) impacted.add(test);
    }
  }

  return [...impacted].sort();
}

function ancestorDirs(dir: string): string[] {
  const parts = dir.split(sep).filter(Boolean);
  const dirs = new Set<string>([dir, dirname(dir)]);
  for (let index = parts.length; index >= 1; index--) dirs.add(parts.slice(0, index).join(sep));
  return [...dirs].filter((value) => value && value !== ".");
}

function sameOrInside(child: string, parent: string): boolean {
  return child === parent || child.startsWith(`${parent}${sep}`);
}

function withoutExtension(file: string): string {
  return file.slice(0, file.length - extname(file).length);
}

function readSmallFile(path: string): string | undefined {
  try {
    if (!existsSync(path)) return undefined;
    const buffer = readFileSync(path);
    if (buffer.byteLength > 250_000) return undefined;
    return buffer.toString("utf8");
  } catch {
    return undefined;
  }
}

function suggestCommands(root: string, tests: string[]): string[] {
  if (tests.length === 0) return [];
  const quotedTests = tests.map(shellQuote).join(" ");
  const packageJson = readPackageJson(root);

  if (packageJson) {
    if (existsSync(join(root, "bun.lock")) || existsSync(join(root, "bun.lockb"))) return [`bun test ${quotedTests}`];
    if (existsSync(join(root, "pnpm-lock.yaml"))) return [`pnpm test -- ${quotedTests}`];
    if (existsSync(join(root, "yarn.lock"))) return [`yarn test ${quotedTests}`];
    return [`npm test -- ${quotedTests}`];
  }

  if (tests.some((test) => test.endsWith(".py"))) return [`pytest ${quotedTests}`];
  if (tests.some((test) => test.endsWith(".rb"))) return [`bundle exec rspec ${quotedTests}`];
  if (tests.some((test) => test.endsWith(".go"))) {
    const packages = [...new Set(tests.map((test) => `./${dirname(test)}`))].join(" ");
    return [`go test ${packages}`];
  }
  if (tests.some((test) => test.endsWith(".rs"))) return ["cargo test"];

  return [];
}

function readPackageJson(root: string): unknown | undefined {
  try {
    return JSON.parse(readFileSync(join(root, "package.json"), "utf8"));
  } catch {
    return undefined;
  }
}

function shellQuote(value: string): string {
  return `'${value.replace(/'/g, `'\\''`)}'`;
}

function isTestCommand(command: string): boolean {
  return /\b(bun|npm|pnpm|yarn)\s+(run\s+)?(test|vitest|jest)\b/.test(command) || /\b(pytest|go\s+test|cargo\s+test|rspec|bundle\s+exec\s+rspec|mvn\s+test|gradle\s+test)\b/.test(command);
}

function isPushOrPrCommand(command: string): boolean {
  return /\bgit\s+push\b/.test(command) || /\bgh\s+pr\s+create\b/.test(command) || /\bhub\s+pull-request\b/.test(command);
}
