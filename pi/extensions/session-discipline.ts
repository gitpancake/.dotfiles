import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

type SessionCounters = {
  toolResults: number;
  toolErrors: number;
  consecutiveErrors: number;
  handoffNotified: boolean;
  errorNotified: boolean;
};

const counters: SessionCounters = {
  toolResults: 0,
  toolErrors: 0,
  consecutiveErrors: 0,
  handoffNotified: false,
  errorNotified: false,
};

export default function sessionDiscipline(pi: ExtensionAPI) {
  pi.on("before_agent_start", async (event) => ({
    systemPrompt: `${event.systemPrompt}\n\n## Pi-native session discipline\n\n- Prefer Pi prompt templates for recurring workflows: /plan, /debug, /prod-debug, /review, /scope, /pickup, /ship, /handoff, /resume.\n- Use /tree, /fork, or /clone before risky refactors, uncertain fixes, or competing approaches. Do not start external workers by habit.\n- Use /compact when the active path is coherent and context is high. Use /handoff before strategy changes, before shipping long-running work, or around 100 tool calls.\n- If repeated tool calls fail for the same reason, stop retrying variants; minimize the failing command/API/path and state the blocker.\n- Keep final updates compact: changed files, focused test command/result, risks, and next step.\n`,
  }));

  pi.on("tool_result", async (event, ctx) => {
    counters.toolResults += 1;

    if (event.isError) {
      counters.toolErrors += 1;
      counters.consecutiveErrors += 1;
      notifyRepeatedErrors(ctx);
      return undefined;
    }

    counters.consecutiveErrors = 0;
    notifyLongSession(ctx);
    return undefined;
  });

  pi.registerCommand("pi-usage", {
    description: "Show current Pi session discipline counters",
    handler: async (_args, ctx) => {
      if (!ctx.hasUI) return;
      ctx.ui.notify(
        `Tools: ${counters.toolResults}, errors: ${counters.toolErrors}, consecutive errors: ${counters.consecutiveErrors}`,
        counters.consecutiveErrors >= 3 ? "warning" : "info",
      );
    },
  });
}

function notifyLongSession(ctx: { hasUI?: boolean; ui?: { notify(message: string, level?: string): void } }) {
  if (counters.handoffNotified) return;
  if (counters.toolResults < 100) return;

  counters.handoffNotified = true;
  if (!ctx.hasUI) return;

  ctx.ui?.notify(
    "Long Pi session: consider /handoff before changing strategy or /compact if the active path is still coherent.",
    "warning",
  );
}

function notifyRepeatedErrors(ctx: { hasUI?: boolean; ui?: { notify(message: string, level?: string): void } }) {
  if (counters.errorNotified) return;
  if (counters.consecutiveErrors < 3) return;

  counters.errorNotified = true;
  if (!ctx.hasUI) return;

  ctx.ui?.notify(
    "Three tool failures in a row: stop retrying variants; minimize the failure and name the blocker.",
    "warning",
  );
}
