// Parallel Planner with Review — four-phase orchestration loop
//
// This template drives a multi-phase workflow:
//   Phase 1 (Plan):             An opus agent analyzes open issues, builds a
//                               dependency graph, and outputs a <plan> JSON
//                               listing unblocked issues with branch names.
//   Phase 2 (Execute + Review): For each issue, a sandbox is created via
//                               createSandbox(). The implementer runs first
//                               (100 iterations). If it produces commits, a
//                               reviewer runs in the same sandbox on the same
//                               branch (1 iteration). All issue pipelines run
//                               concurrently via Promise.allSettled().
//   Phase 3 (Merge):            A single agent merges all completed branches
//                               into the current branch.
//
// The outer loop repeats up to MAX_ITERATIONS times so that newly unblocked
// issues are picked up after each round of merges.
//
// Usage:
//   npx tsx .sandcastle/main.mts
// Or add to package.json:
//   "scripts": { "sandcastle": "npx tsx .sandcastle/main.mts" }

import * as sandcastle from "@ai-hero/sandcastle";
import { docker } from "@ai-hero/sandcastle/sandboxes/docker";
import { execFile } from "node:child_process";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

// Maximum number of plan→execute→merge cycles before stopping.
// Raise this if your backlog is large; lower it for a quick smoke-test run.
const MAX_ITERATIONS = Number(process.env.SANDCASTLE_MAX_ITERATIONS ?? "10");

// Hooks run inside the sandbox before the agent starts each iteration.
// uv sync ensures the sandbox always has fresh Python dependencies.
const hooks = {
  sandbox: {
    onSandboxReady: [
      {
        command: "bash -lc 'uv sync --all-groups && command -v python3 && command -v rg && command -v gh'",
        timeoutMs: 30 * 60_000,
      },
    ],
  },
};

const copyToWorktree: string[] = [];

const sandboxProvider = docker({
  imageName: "sandcastle:fitness-tracker",
  mounts: [{ hostPath: "~/.codex", sandboxPath: "/home/agent/.codex" }],
});

const AGENT_IDLE_TIMEOUT_SECONDS = 7.5 * 60;
const COMPLETION_SIGNAL = "<promise>COMPLETE</promise>";

async function branchAheadCount(
  targetBranch: string,
  branch: string,
): Promise<number | null> {
  try {
    const { stdout } = await execFileAsync("git", [
      "rev-list",
      "--count",
      `${targetBranch}..${branch}`,
    ]);
    return Number(stdout.trim());
  } catch {
    return null;
  }
}

async function targetContainsIssue(
  targetBranch: string,
  issueId: string,
): Promise<boolean> {
  const { stdout } = await execFileAsync("git", [
    "log",
    "--max-count=1",
    "--format=%H",
    `--grep=GH-${issueId}`,
    `--grep=#${issueId}`,
    `--grep=issue ${issueId}`,
    targetBranch,
  ]);
  return stdout.trim().length > 0;
}

const { stdout: targetBranchOut } = await execFileAsync("git", [
  "branch",
  "--show-current",
]);
const targetBranch = targetBranchOut.trim();

// ---------------------------------------------------------------------------
// Main loop
// ---------------------------------------------------------------------------

for (let iteration = 1; iteration <= MAX_ITERATIONS; iteration++) {
  console.log(`\n=== Iteration ${iteration}/${MAX_ITERATIONS} ===\n`);

  // -------------------------------------------------------------------------
  // Phase 1: Plan
  //
  // The planning agent (opus, for deeper reasoning) reads the open issue list,
  // builds a dependency graph, and selects the issues that can be worked in
  // parallel right now (i.e., no blocking dependencies on other open issues).
  //
  // It outputs a <plan> JSON block — we parse that to drive Phase 2.
  // -------------------------------------------------------------------------
  const plan = await sandcastle.run({
    hooks,
    sandbox: sandboxProvider,
    name: "planner",
    // One iteration is enough: the planner just needs to read and reason,
    // not write code.
    maxIterations: 1,
    // Opus for planning: dependency analysis benefits from deeper reasoning.
    agent: sandcastle.codex("gpt-5.5"),
    promptFile: "./.sandcastle/plan-prompt.md",
    completionSignal: "</plan>",
    idleTimeoutSeconds: AGENT_IDLE_TIMEOUT_SECONDS,
  });

  // Extract the <plan>…</plan> block from the agent's stdout.
  const planMatch = plan.stdout.match(/<plan>([\s\S]*?)<\/plan>/);
  if (!planMatch) {
    throw new Error(
      "Planning agent did not produce a <plan> tag.\n\n" + plan.stdout,
    );
  }

  // The plan JSON contains an array of issues, each with id, title, branch.
  const { issues } = JSON.parse(planMatch[1]!) as {
    issues: { id: string; title: string; branch: string }[];
  };

  if (issues.length === 0) {
    // No unblocked work — either everything is done or everything is blocked.
    console.log("No unblocked issues to work on. Exiting.");
    break;
  }

  console.log(
    `Planning complete. ${issues.length} issue(s) to work in parallel:`,
  );
  for (const issue of issues) {
    console.log(`  ${issue.id}: ${issue.title} → ${issue.branch}`);
  }

  // -------------------------------------------------------------------------
  // Phase 2: Execute + Review
  //
  // For each issue, create a sandbox via createSandbox() so the implementer
  // and reviewer share the same sandbox instance per branch. The implementer
  // runs first; if it produces commits, the reviewer runs in the same sandbox.
  //
  // Promise.allSettled means one failing pipeline doesn't cancel the others.
  // -------------------------------------------------------------------------

  const mergeReadyIssues: typeof issues = [];
  const implementationIssues: typeof issues = [];

  for (const issue of issues) {
    const aheadCount = await branchAheadCount(targetBranch, issue.branch);
    if (aheadCount === null) {
      implementationIssues.push(issue);
    } else if (aheadCount === 0) {
      if (await targetContainsIssue(targetBranch, issue.id)) {
        console.log(
          `  ${issue.id}: branch ${issue.branch} already merged — skipping`,
        );
      } else {
        console.log(
          `  ${issue.id}: branch ${issue.branch} has no unmerged commits — rerunning implementer`,
        );
        implementationIssues.push(issue);
      }
    } else {
      console.log(
        `  ${issue.id}: branch ${issue.branch} already has ${aheadCount} unmerged commit(s) — queueing for merge`,
      );
      mergeReadyIssues.push(issue);
    }
  }

  if (implementationIssues.length === 0 && mergeReadyIssues.length === 0) {
    console.log(
      "All planned issues were already merged. Continuing to next iteration.",
    );
    continue;
  }

  const settled = await Promise.allSettled(
    implementationIssues.map(async (issue) => {
      const sandbox = await sandcastle.createSandbox({
        branch: issue.branch,
        sandbox: sandboxProvider,
        hooks,
        copyToWorktree,
      });

      try {
        // Run the implementer
        const implement = await sandbox.run({
          name: "implementer",
          maxIterations: 100,
          idleTimeoutSeconds: AGENT_IDLE_TIMEOUT_SECONDS,
          agent: sandcastle.codex("gpt-5.5"),
          promptFile: "./.sandcastle/implement-prompt.md",
          completionSignal: COMPLETION_SIGNAL,
          promptArgs: {
            TASK_ID: issue.id,
            ISSUE_TITLE: issue.title,
            BRANCH: issue.branch,
          },
        });

        // Only review if the implementer produced commits
        if (implement.commits.length > 0) {
          const review = await sandbox.run({
            name: "reviewer",
            maxIterations: 1,
            idleTimeoutSeconds: AGENT_IDLE_TIMEOUT_SECONDS,
            agent: sandcastle.codex("gpt-5.5"),
            promptFile: "./.sandcastle/review-prompt.md",
            completionSignal: COMPLETION_SIGNAL,
            promptArgs: {
              TASK_ID: issue.id,
              ISSUE_TITLE: issue.title,
              BRANCH: issue.branch,
              TARGET_BRANCH: targetBranch,
            },
          });

          // Merge commits from both runs so the merge phase sees all of them.
          // Each sandbox.run() only returns commits from its own run.
          return {
            ...review,
            commits: [...implement.commits, ...review.commits],
          };
        }

        return implement;
      } finally {
        await sandbox.close();
      }
    }),
  );

  // Log any agents that threw (network error, sandbox crash, etc.).
  for (const [i, outcome] of settled.entries()) {
    if (outcome.status === "rejected") {
      console.error(
        `  ✗ ${implementationIssues[i]!.id} (${implementationIssues[i]!.branch}) failed: ${outcome.reason}`,
      );
    }
  }

  // Only pass branches that actually produced commits to the merge phase.
  // An agent that ran successfully but made no commits has nothing to merge.
  const completedIssues = [
    ...mergeReadyIssues,
    ...settled
      .map((outcome, i) => ({ outcome, issue: implementationIssues[i]! }))
      .filter(
        (entry) =>
          entry.outcome.status === "fulfilled" &&
          entry.outcome.value.commits.length > 0,
      )
      .map((entry) => entry.issue),
  ];

  const completedBranches = completedIssues.map((i) => i.branch);

  console.log(
    `\nExecution complete. ${completedBranches.length} branch(es) with commits:`,
  );
  for (const branch of completedBranches) {
    console.log(`  ${branch}`);
  }

  if (completedBranches.length === 0) {
    // All agents ran but none made commits — nothing to merge this cycle.
    console.log("No commits produced. Nothing to merge.");
    continue;
  }

  // -------------------------------------------------------------------------
  // Phase 3: Merge
  //
  // One agent merges all completed branches into the current branch,
  // resolving any conflicts and running tests to confirm everything works.
  //
  // The {{BRANCHES}} and {{ISSUES}} prompt arguments are lists that the agent
  // uses to know which branches to merge and which issues to close.
  // -------------------------------------------------------------------------
  await sandcastle.run({
    hooks,
    sandbox: sandboxProvider,
    name: "merger",
    maxIterations: 1,
    idleTimeoutSeconds: AGENT_IDLE_TIMEOUT_SECONDS,
    agent: sandcastle.codex("gpt-5.5"),
    promptFile: "./.sandcastle/merge-prompt.md",
    completionSignal: COMPLETION_SIGNAL,
    promptArgs: {
      // A markdown list of branch names, one per line.
      BRANCHES: completedBranches.map((b) => `- ${b}`).join("\n"),
      // A markdown list of issue IDs and titles, one per line.
      ISSUES: completedIssues
        .map((i) => `- ${i.id}: ${i.title}`)
        .join("\n"),
    },
  });

  console.log("\nBranches merged.");
}

console.log("\nAll done.");
