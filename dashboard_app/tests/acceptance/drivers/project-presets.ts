/**
 * Named fixture projects. Each preset documents the facts its scenarios rely
 * on; the scenarios restate the values they assert so each test reads alone.
 *
 * FULL — every artifact family present, with something needing attention:
 *   sentinel   3 runs; newest 2026-10-01 09:30Z: grade C [PARTIAL], coherence A,
 *              findings 1 critical / 2 important / 3 suggested, 3 checks
 *              [not reached] (CA02, P04, CH01); earlier runs A (09-20), B (09-26)
 *   metrics    2 snapshots (09-21, 09-28 12:00Z), every indicator worse in the
 *              newer one; readiness level 3 at 82 %
 *   evals      3 quality-eval runs (09-10, 09-18, newest 09-30 08:00Z); newest:
 *              1187 PASS / 64 WARN / 3 FAIL / 9 SKIP, 271 judged calls, 17 cache
 *              hits, 812,345 tokens in / 23,456 out, $0.4321; failures:
 *              adr_body_sections ×2, task_artifact_manifest ×1; warnings:
 *              affected_reqs_resolvability ×4, adr_staleness ×2
 *              eval ledger: leaderboard-shaped, 09-15
 *   workshops  alpha-active (3 h ago, 2/5), beta-active (WIP 20 d old but
 *              PROGRESS 2 d ago, 1/3), gamma-stale (12 d, 4/6), delta-done
 *              (finished 1 d ago), epsilon-done (finished 30 d ago)
 *   decisions  finalized dec-007, dec-009, dec-010, dec-012 + 2 drafts; dec-007
 *              is the most recently modified (09-25), dec-012 the highest number
 *   tech debt  td-001 important open, td-002 suggested open (09-27)
 *   knowledge  ROADMAP.md 09-05; DESIGN.md 09-12, docs/architecture.md 09-14;
 *              doc manifest + docs/guide.md 09-08 10:00Z
 *   newest artifact overall: alpha-active's WIP.md, today 12:00Z
 *
 * CLEAN — every family present and nothing needing attention: sentinel grade A
 *   with no critical or important finding, a single metrics snapshot (baseline),
 *   a quality-eval run with no failure, only suggested tech debt.
 *
 * PARTIAL — only the sentinel and workshops families.
 *
 * EMPTY — an empty `.ai-state/` and nothing else.
 */

import {
  at,
  baselineLedger,
  buildProjectRoot,
  daysAgo,
  decision,
  DEGRADED_METRICS,
  designDocs,
  documentationManifest,
  type FixtureFile,
  HEALTHY_METRICS,
  hoursAgo,
  leaderboardLedger,
  metricsFamily,
  qualityEvalFamily,
  type QualityEvalRun,
  roadmap,
  sentinelFamily,
  type SentinelRun,
  techDebtLedger,
  unreadable,
  workshop
} from "./fixture-project";

export const FULL_SENTINEL_RUNS: SentinelRun[] = [
  { at: at("2026-09-20T10:00:00Z"), grade: "A", coherence: "A", critical: 0, important: 1, suggested: 2 },
  { at: at("2026-09-26T10:00:00Z"), grade: "B", coherence: "A", critical: 0, important: 2, suggested: 3 },
  {
    at: at("2026-10-01T09:30:00Z"),
    grade: "C",
    coherence: "A",
    critical: 1,
    important: 2,
    suggested: 3,
    partial: true,
    notReached: ["CA02", "P04", "CH01"]
  }
];

const passRows = (n: number) =>
  Array.from({ length: n }, (_, i) => ({
    check: "adr_frontmatter_completeness",
    verdict: "PASS" as const,
    artifact: `.ai-state/decisions/pass-record-${"abcdefgh"[i]}.md`,
    finding: "All required frontmatter fields present."
  }));

export const FULL_EVAL_RUNS: QualityEvalRun[] = [
  {
    at: at("2026-09-10T08:00:00Z"),
    target: "git:1111111 (1111111)",
    pass: 1100,
    warn: 70,
    fail: 9,
    skip: 2,
    costUsd: 0,
    rows: passRows(2)
  },
  {
    at: at("2026-09-18T08:00:00Z"),
    target: "git:2222222 (2222222)",
    pass: 1150,
    warn: 66,
    fail: 5,
    skip: 2,
    costUsd: 0,
    rows: passRows(2)
  },
  {
    at: at("2026-09-30T08:00:00Z"),
    target: "/work/praxion",
    pass: 1187,
    warn: 64,
    fail: 3,
    skip: 9,
    costUsd: 0.4321,
    judged: { calls: 271, cacheHits: 17, tokensIn: 812_345, tokensOut: 23_456 },
    calibrationNote: "Family one calibration: unresolvable affected_reqs entries emit WARN by design.",
    rows: [
      ...passRows(3),
      {
        check: "adr_body_sections",
        verdict: "FAIL",
        artifact: ".ai-state/decisions/missing-context.md",
        finding: "Missing Context section."
      },
      {
        check: "adr_body_sections",
        verdict: "FAIL",
        artifact: ".ai-state/decisions/missing-decision.md",
        finding: "Missing Decision section."
      },
      {
        check: "task_artifact_manifest",
        verdict: "FAIL",
        artifact: ".ai-work/some-task/VERIFICATION_REPORT.md",
        finding: "Expected required artifact missing."
      },
      ...["alpha", "beta", "gamma", "delta"].map((name) => ({
        check: "affected_reqs_resolvability",
        verdict: "WARN" as const,
        artifact: `.ai-state/decisions/warned-${name}.md`,
        finding: "Unresolvable affected_reqs entry."
      })),
      ...["epsilon", "zeta"].map((name) => ({
        check: "adr_staleness",
        verdict: "WARN" as const,
        artifact: `.ai-state/decisions/stale-${name}.md`,
        finding: "Not revisited in a year."
      }))
    ]
  }
];

const FULL_WORKSHOPS: FixtureFile[] = [
  ...workshop({
    slug: "alpha-active",
    finished: false,
    currentStep: "Wire the alpha reader",
    done: 2,
    total: 5,
    files: { "WIP.md": hoursAgo(3) }
  }),
  ...workshop({
    slug: "beta-active",
    finished: false,
    currentStep: "Draft the beta tests",
    done: 1,
    total: 3,
    files: { "WIP.md": daysAgo(20), "PROGRESS.md": daysAgo(2) }
  }),
  ...workshop({
    slug: "gamma-stale",
    finished: false,
    currentStep: "Abandoned gamma step",
    done: 4,
    total: 6,
    files: { "WIP.md": daysAgo(12) }
  }),
  ...workshop({
    slug: "delta-done",
    finished: true,
    currentStep: "Done",
    done: 3,
    total: 3,
    files: { "WIP.md": daysAgo(1) }
  }),
  ...workshop({
    slug: "epsilon-done",
    finished: true,
    currentStep: "Done",
    done: 2,
    total: 2,
    files: { "WIP.md": daysAgo(30) }
  })
];

const FULL_DECISIONS: FixtureFile[] = [
  decision({ number: 7, title: "Seven implementation choice", category: "implementation", mtime: at("2026-09-25T10:00:00Z") }),
  decision({ number: 9, title: "Nine architectural boundary", category: "architectural", mtime: at("2026-09-02T10:00:00Z") }),
  decision({ number: 10, title: "Ten behavioral rule", category: "behavioral", mtime: at("2026-09-03T10:00:00Z") }),
  decision({ number: 12, title: "Twelve architectural split", category: "architectural", mtime: at("2026-09-04T10:00:00Z") }),
  decision({ draftHash: "aaaa1111", title: "Draft configuration knob", category: "configuration", mtime: at("2026-09-21T10:00:00Z") }),
  decision({ draftHash: "bbbb2222", title: "Draft behavioral tweak", category: "behavioral", mtime: at("2026-09-22T10:00:00Z") })
];

export function fullProjectFiles(): FixtureFile[] {
  return [
    ...sentinelFamily(FULL_SENTINEL_RUNS),
    ...metricsFamily([
      { at: at("2026-09-21T12:00:00Z"), ...HEALTHY_METRICS },
      { at: at("2026-09-28T12:00:00Z"), ...DEGRADED_METRICS }
    ]),
    ...qualityEvalFamily(FULL_EVAL_RUNS),
    leaderboardLedger(at("2026-09-15T10:00:00Z")),
    ...FULL_WORKSHOPS,
    ...FULL_DECISIONS,
    techDebtLedger(
      [
        { id: "td-001", severity: "important", status: "open", note: "An important open debt" },
        { id: "td-002", severity: "suggested", status: "open", note: "A suggested open debt" }
      ],
      at("2026-09-27T10:00:00Z")
    ),
    roadmap(at("2026-09-05T10:00:00Z")),
    ...designDocs(at("2026-09-12T10:00:00Z"), at("2026-09-14T10:00:00Z")),
    ...documentationManifest(at("2026-09-08T10:00:00Z"))
  ];
}

export function fullProject(): Promise<string> {
  return buildProjectRoot(fullProjectFiles(), "acceptance-full-");
}

/** FULL with the quality-eval log unreadable (a directory in its place). */
export function fullProjectWithUnreadableEvalLog(): Promise<string> {
  const files = fullProjectFiles().filter((f) => !f.path.endsWith("PRAXION_EVAL_LOG.md"));
  return buildProjectRoot([...files, unreadable(".ai-state/praxion_eval_reports/PRAXION_EVAL_LOG.md")], "acceptance-unreadable-");
}

/** FULL with the eval ledger in a non-leaderboard shape. */
export function fullProjectWithBaselineLedger(): Promise<string> {
  const files = fullProjectFiles().filter((f) => !f.path.endsWith("eval_ledger/EVAL_LOG.md"));
  return buildProjectRoot([...files, baselineLedger(at("2026-09-15T10:00:00Z"))], "acceptance-baseline-ledger-");
}

/** FULL without any eval ledger. */
export function fullProjectWithoutLedger(): Promise<string> {
  const files = fullProjectFiles().filter((f) => !f.path.endsWith("eval_ledger/EVAL_LOG.md"));
  return buildProjectRoot(files, "acceptance-no-ledger-");
}

export function cleanProject(): Promise<string> {
  return buildProjectRoot(
    [
      ...sentinelFamily([
        { at: at("2026-09-26T10:00:00Z"), grade: "B", coherence: "A", critical: 0, important: 1, suggested: 4 },
        { at: at("2026-10-01T09:30:00Z"), grade: "A", coherence: "A", critical: 0, important: 0, suggested: 2 }
      ]),
      ...metricsFamily([{ at: at("2026-09-28T12:00:00Z"), ...HEALTHY_METRICS }]),
      ...qualityEvalFamily([
        {
          at: at("2026-09-30T08:00:00Z"),
          target: "/work/praxion",
          pass: 1200,
          warn: 10,
          fail: 0,
          skip: 1,
          costUsd: 0,
          rows: passRows(2)
        }
      ]),
      ...workshop({
        slug: "alpha-active",
        finished: false,
        currentStep: "Wire the alpha reader",
        done: 2,
        total: 5,
        files: { "WIP.md": hoursAgo(3) }
      }),
      decision({ number: 1, title: "First decision", category: "architectural", mtime: at("2026-09-02T10:00:00Z") }),
      techDebtLedger(
        [{ id: "td-002", severity: "suggested", status: "open", note: "A suggested open debt" }],
        at("2026-09-27T10:00:00Z")
      )
    ],
    "acceptance-clean-"
  );
}

export function partialProject(): Promise<string> {
  return buildProjectRoot([...sentinelFamily(FULL_SENTINEL_RUNS), ...FULL_WORKSHOPS], "acceptance-partial-");
}

export function emptyProject(): Promise<string> {
  return buildProjectRoot([], "acceptance-empty-");
}
