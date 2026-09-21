export const meta = {
  name: 'lens-fanout',
  description: 'Isolated lens collection, then one reconciliation pass.',
  phases: [
    { title: 'Collect', detail: 'One agent per lens; no agent can read a sibling.' },
    { title: 'Reconcile', detail: 'One aggregator reads the fragments and maps divergence.' }
  ],
  whenToUse: 'Launched by the /lens-fanout skill after the honest-uncertainty gate fires.'
};   // PURE LITERAL -- no variables, no calls, no interpolation; the harness requires it first in the file

// Fans N isolated lens agents out in parallel, then reconciles them through one
// aggregator. Plain JavaScript (no TS annotations, no Node APIs, no filesystem);
// every artifact write is an explicit instruction inside an agent() prompt, never
// a script-side write, because this script has no filesystem access.

const LENS_SCHEMA = {
  type: 'object',
  properties: {
    marker: { type: 'string', enum: ['[COMPLETE]', '[PARTIAL]', '[BLOCKED]'] },
    lens: { type: 'string' },
    fragment_path: { type: 'string' },
    claims_count: { type: 'integer' },
    certainty: { type: 'string', enum: ['high', 'medium', 'low'] },
    summary: { type: 'string' }
  },
  required: ['marker', 'lens', 'fragment_path', 'claims_count', 'certainty', 'summary']
};

const RUN_SCHEMA = {
  type: 'object',
  properties: {
    marker: { type: 'string', enum: ['[COMPLETE]', '[PARTIAL]', '[BLOCKED]'] },
    findings_path: { type: 'string' },
    divergence_count: { type: 'integer' },
    lenses_read: { type: 'integer' },
    unresolved: { type: 'array', items: { type: 'string' } }
  },
  required: ['marker', 'findings_path', 'divergence_count', 'lenses_read']
};

// --- guard the envelope (the only code that runs post-launch) ---
const lenses = Array.isArray(args.lenses) ? args.lenses : [];
const names = lenses.map(l => l && l.name);
if (lenses.length < 2 || lenses.length > 6 || new Set(names).size !== names.length) {
  log(`refusing: need 2..6 uniquely-named lenses, got ${JSON.stringify(names)}`);
  return { marker: '[BLOCKED]', reason: 'lens-set-invalid', lenses: [], dropped: names };
}
log(`lens-fanout: ${lenses.length} lenses on slug ${args.slug} (${args.timestamp})`);

// --- Collect: the isolation guarantee lives in this closure set ---
const proposer = args.proposer_model ? { model: args.proposer_model } : {};
const collected = await parallel(lenses.map(lens => () => agent(
  lensPrompt(lens),                         // closes over `lens`, `args` -- never over `collected`
  { label: lens.name, phase: 'Collect', schema: LENS_SCHEMA, ...proposer }
)));

// --- no silent caps: name what dropped, then filter ---
const dropped = lenses.filter((_, i) => !collected[i]).map(l => l.name);
if (dropped.length) {
  log(`dropped ${dropped.length}/${lenses.length}: ${dropped.join(', ')} (agent returned null -- user skip or terminal API error)`);
}
const rows = collected.filter(Boolean);
if (rows.length < 2) {
  return { marker: '[BLOCKED]', reason: 'fewer-than-two-lenses-survived', lenses: rows, dropped, timestamp: args.timestamp };
}

// --- Reconcile: the justified barrier -- the aggregator needs every lens before it can compare them ---
const synthesis = await agent(
  aggregatorPrompt(rows, dropped),          // passes PATHS and markers, not lens prose
  { label: 'reconcile', phase: 'Reconcile', schema: RUN_SCHEMA, effort: 'high' }   // model omitted -> session model
);
if (!synthesis) {
  return { marker: '[PARTIAL]', reason: 'aggregator-returned-null', lenses: pointerRows(rows), dropped, timestamp: args.timestamp };
}

// --- pointer, never payload (no lens `summary` crosses back -- the omission is the design) ---
return {
  marker: synthesis.marker,
  findings_path: synthesis.findings_path,
  divergence_count: synthesis.divergence_count,
  lenses_read: synthesis.lenses_read,
  lenses: pointerRows(rows),
  dropped,
  timestamp: args.timestamp
};

// --- prompt builders: pure functions of `args` and their own arguments ---

function lensPrompt(lens) {
  const sourcesLine = (args.sources && args.sources.length)
    ? `Shared sources (identical for every lens): ${args.sources.join(', ')}`
    : 'No shared sources were provided; ground findings in the question and your own lens.';
  return [
    `Task slug: ${args.slug}. Use absolute paths under the repo worktree root for every file write; never a relative path.`,
    `If it exists, read .ai-work/${args.slug}/TASK_BRIEF.md first -- it may not have reached you (a hook-delivered brief does not fire for workflow agents).`,
    '',
    'Behavioral contract (four non-negotiable behaviors; full text at rules/swe/agent-behavioral-contract.md):',
    '- Surface Assumptions: state your interpretation and each gap-filling assumption as you make it.',
    '- Register Objection: state a conflict with a reason before complying or declining.',
    '- Stay Surgical: touch only what this lens requires.',
    '- Simplicity First: prefer the smallest finding set that meets the lens brief.',
    '',
    `Question: ${args.question}`,
    `Your lens: ${lens.name} -- ${lens.brief}`,
    'This is your only framing. Never name, quote, or infer another lens; you have no visibility into any sibling and must not invent one.',
    sourcesLine,
    'For per-claim confidence tiers, see skills/multi-perspective-analysis/references/calibrated-confidence.md.',
    `Write your findings to exactly .ai-work/${args.slug}/RESEARCH_${lens.name}.md and nothing else.`,
    'Return marker, lens, fragment_path, claims_count, certainty, and a summary of 200 characters or fewer.'
  ].join('\n');
}

function aggregatorPrompt(rows, dropped) {
  const roster = rows
    .map(r => `- ${r.lens} (${r.marker}, certainty ${r.certainty}, ${r.claims_count} claims): ${r.fragment_path}`)
    .join('\n');
  const droppedLine = dropped.length
    ? `Dropped lenses (not read, do not wait for them): ${dropped.join(', ')}.`
    : 'No lenses were dropped.';
  return [
    `Task slug: ${args.slug}. Use absolute paths under the repo worktree root for every file write; never a relative path.`,
    '',
    'Behavioral contract (four non-negotiable behaviors; full text at rules/swe/agent-behavioral-contract.md):',
    '- Surface Assumptions: state your interpretation and each gap-filling assumption as you make it.',
    '- Register Objection: state a conflict with a reason before complying or declining.',
    '- Stay Surgical: touch only what reconciliation requires.',
    '- Simplicity First: prefer the smallest synthesis that meets the question.',
    '',
    `Question: ${args.question}`,
    'Read every fragment below from disk before writing anything -- do not rely on this prompt for their content:',
    roster,
    droppedLine,
    `Write .ai-work/${args.slug}/RESEARCH_FINDINGS.md with a "## Divergence Map" section recording agreements, surviving contradictions and blind spots across the lenses above. Preserve contradictions -- never average or homogenise them.`,
    'Return marker, findings_path, divergence_count, lenses_read, and unresolved (array of open questions; may be empty).'
  ].join('\n');
}

function pointerRows(rows) {
  return rows.map(({ lens, marker, fragment_path, claims_count, certainty }) => (
    { lens, marker, fragment_path, claims_count, certainty }
  ));
}
