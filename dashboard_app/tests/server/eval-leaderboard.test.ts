import { describe, expect, it } from "vitest";

import type { EvalLeaderboardData, EvalLogRow, EvalSortKey } from "@/lib/evals";
import {
  filterEvalRowsByTask,
  formatEvalCost,
  formatEvalMetric,
  sortEvalRows
} from "@/lib/evals";
import { parseEvalsLog } from "@/server/view-models/evals";

// ---------------------------------------------------------------------------
// Fixtures derived from the Minimal Valid Example in
// skills/agent-evals/references/run-ledger-schema.md § Minimal EVAL_LOG.md Row
// ---------------------------------------------------------------------------

const MINIMAL_LOG_TABLE = `
| run_id | task | generation | primary_metric | held_out_delta | model_id | prompt_hash | dataset_sha | cost_usd | git_sha | store_uri |
|---|---|---|---|---|---|---|---|---|---|---|
| eval-swebench-g3-a4b2c1 | swebench_verified | 3 | 0.641 | -0.012 | claude-sonnet-4-5 | f3a9d2b7 | 9e3c2a1b | 7.23 | a1b2c3d | ~/.myproject/runs/eval-swebench-g3-a4b2c1/ |
`.trim();

const TWO_ROW_TABLE = `
| run_id | task | generation | primary_metric | held_out_delta | model_id | prompt_hash | dataset_sha | cost_usd | git_sha | store_uri |
|---|---|---|---|---|---|---|---|---|---|---|
| eval-swebench-g3-a4b2c1 | swebench_verified | 3 | 0.641 | -0.012 | claude-sonnet-4-5 | f3a9d2b7 | 9e3c2a1b | 7.23 | a1b2c3d | ~/.myproject/runs/eval-swebench-g3-a4b2c1/ |
| eval-swebench-g1-bb0011 | swebench_verified | 1 | 0.512 | 0.003 | claude-opus-4 | aa11bb22 | cc33dd44 | 12.50 | b2c3d4e | ~/.myproject/runs/eval-swebench-g1-bb0011/ |
`.trim();

// ---------------------------------------------------------------------------
// parseEvalsLog
// ---------------------------------------------------------------------------

describe("parseEvalsLog — well-formed table from schema example", () => {
  it("parses a single-row EVAL_LOG.md table into a typed EvalLogRow array", () => {
    const rows = parseEvalsLog(MINIMAL_LOG_TABLE);

    expect(rows).toHaveLength(1);
    const row = rows[0];
    expect(row?.run_id).toBe("eval-swebench-g3-a4b2c1");
    expect(row?.task).toBe("swebench_verified");
    expect(row?.generation).toBe(3);
    expect(row?.primary_metric).toBe(0.641);
    expect(row?.held_out_delta).toBe(-0.012);
    expect(row?.model_id).toBe("claude-sonnet-4-5");
    expect(row?.prompt_hash).toBe("f3a9d2b7");
    expect(row?.dataset_sha).toBe("9e3c2a1b");
    expect(row?.cost_usd).toBe(7.23);
    expect(row?.git_sha).toBe("a1b2c3d");
    expect(row?.store_uri).toBe("~/.myproject/runs/eval-swebench-g3-a4b2c1/");
  });

  it("coerces string numeric columns to number types", () => {
    const rows = parseEvalsLog(MINIMAL_LOG_TABLE);
    const row = rows[0];
    expect(typeof row?.generation).toBe("number");
    expect(typeof row?.primary_metric).toBe("number");
    expect(typeof row?.held_out_delta).toBe("number");
    expect(typeof row?.cost_usd).toBe("number");
  });

  it("parses two-row table producing two rows in document order", () => {
    const rows = parseEvalsLog(TWO_ROW_TABLE);
    expect(rows).toHaveLength(2);
    expect(rows[0]?.run_id).toBe("eval-swebench-g3-a4b2c1");
    expect(rows[1]?.run_id).toBe("eval-swebench-g1-bb0011");
  });
});

describe("parseEvalsLog — empty and missing input", () => {
  it("returns empty array for empty string without throwing", () => {
    expect(parseEvalsLog("")).toEqual([]);
  });

  it("returns empty array for whitespace-only string", () => {
    expect(parseEvalsLog("   \n\n   ")).toEqual([]);
  });

  it("returns empty array for a string with only the header row (no data)", () => {
    const headerOnly =
      "| run_id | task | generation | primary_metric | held_out_delta | model_id | prompt_hash | dataset_sha | cost_usd | git_sha | store_uri |";
    expect(parseEvalsLog(headerOnly)).toEqual([]);
  });

  it("returns empty array for non-table prose", () => {
    expect(parseEvalsLog("# EVAL_LOG\n\nNo runs yet.\n")).toEqual([]);
  });
});

describe("parseEvalsLog — column coercion edge cases", () => {
  it("coerces a blank numeric cell to null", () => {
    const tableWithBlankCells = `
| run_id | task | generation | primary_metric | held_out_delta | model_id | prompt_hash | dataset_sha | cost_usd | git_sha | store_uri |
|---|---|---|---|---|---|---|---|---|---|---|
| r-missing |  |  |  |  |  |  |  |  |  |  |
`.trim();
    const rows = parseEvalsLog(tableWithBlankCells);
    expect(rows).toHaveLength(1);
    const row = rows[0];
    expect(row?.generation).toBeNull();
    expect(row?.primary_metric).toBeNull();
    expect(row?.held_out_delta).toBeNull();
    expect(row?.cost_usd).toBeNull();
    expect(row?.task).toBeNull();
  });

  it("coerces a non-numeric value in a numeric column to null", () => {
    const tableWithGarbage = `
| run_id | task | generation | primary_metric | held_out_delta | model_id | prompt_hash | dataset_sha | cost_usd | git_sha | store_uri |
|---|---|---|---|---|---|---|---|---|---|---|
| r-bad | task-x | gen3 | not-a-number | — | model-y | hash1 | sha1 | bad | abc | /store/ |
`.trim();
    const rows = parseEvalsLog(tableWithGarbage);
    expect(rows).toHaveLength(1);
    const row = rows[0];
    expect(row?.generation).toBeNull();
    expect(row?.primary_metric).toBeNull();
    expect(row?.cost_usd).toBeNull();
    // String columns survive
    expect(row?.task).toBe("task-x");
    expect(row?.model_id).toBe("model-y");
  });

  it("preserves a negative numeric value in held_out_delta", () => {
    const rows = parseEvalsLog(MINIMAL_LOG_TABLE);
    expect(rows[0]?.held_out_delta).toBe(-0.012);
  });

  it("returns null for string columns that are blank", () => {
    const tableWithBlank = `
| run_id | task | generation | primary_metric | held_out_delta | model_id | prompt_hash | dataset_sha | cost_usd | git_sha | store_uri |
|---|---|---|---|---|---|---|---|---|---|---|
|  | some_task | 1 | 0.5 | 0.0 | m | h | d | 0.0 | g | /s/ |
`.trim();
    const rows = parseEvalsLog(tableWithBlank);
    expect(rows[0]?.run_id).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// sortEvalRows
// ---------------------------------------------------------------------------

function makeRow(overrides: Partial<EvalLogRow>): EvalLogRow {
  return {
    run_id: null,
    task: null,
    generation: null,
    primary_metric: null,
    held_out_delta: null,
    model_id: null,
    prompt_hash: null,
    dataset_sha: null,
    cost_usd: null,
    git_sha: null,
    store_uri: null,
    ...overrides
  };
}

describe("sortEvalRows — primary_metric descending", () => {
  it("ranks rows from highest to lowest primary_metric", () => {
    const rows = [
      makeRow({ run_id: "a", primary_metric: 0.512 }),
      makeRow({ run_id: "b", primary_metric: 0.641 }),
      makeRow({ run_id: "c", primary_metric: 0.599 })
    ];
    const sorted = sortEvalRows(rows, "primary_metric");
    expect(sorted.map((r) => r.run_id)).toEqual(["b", "c", "a"]);
  });

  it("places rows with null primary_metric at the end", () => {
    const rows = [
      makeRow({ run_id: "null-row", primary_metric: null }),
      makeRow({ run_id: "good-row", primary_metric: 0.7 })
    ];
    const sorted = sortEvalRows(rows, "primary_metric");
    expect(sorted[0]?.run_id).toBe("good-row");
    expect(sorted[1]?.run_id).toBe("null-row");
  });

  it("places two null primary_metric rows both at the end (stable relative to each other)", () => {
    const rows = [
      makeRow({ run_id: "null-1", primary_metric: null }),
      makeRow({ run_id: "good", primary_metric: 0.5 }),
      makeRow({ run_id: "null-2", primary_metric: null })
    ];
    const sorted = sortEvalRows(rows, "primary_metric");
    expect(sorted[0]?.run_id).toBe("good");
    // Both nulls appear at the tail
    expect(sorted.slice(1).every((r) => r.primary_metric === null)).toBe(true);
  });
});

describe("sortEvalRows — generation descending", () => {
  it("ranks rows from highest generation to lowest", () => {
    const rows = [
      makeRow({ run_id: "g1", generation: 1 }),
      makeRow({ run_id: "g3", generation: 3 }),
      makeRow({ run_id: "g2", generation: 2 })
    ];
    const sorted = sortEvalRows(rows, "generation");
    expect(sorted.map((r) => r.run_id)).toEqual(["g3", "g2", "g1"]);
  });
});

describe("sortEvalRows — cost_usd descending", () => {
  it("ranks rows from highest cost to lowest cost", () => {
    const rows = [
      makeRow({ run_id: "cheap", cost_usd: 1.5 }),
      makeRow({ run_id: "expensive", cost_usd: 12.5 }),
      makeRow({ run_id: "mid", cost_usd: 7.23 })
    ];
    const sorted = sortEvalRows(rows, "cost_usd");
    expect(sorted.map((r) => r.run_id)).toEqual(["expensive", "mid", "cheap"]);
  });
});

describe("sortEvalRows — empty input", () => {
  it("returns empty array when given an empty array", () => {
    expect(sortEvalRows([], "primary_metric")).toEqual([]);
  });
});

describe("sortEvalRows — does not mutate input array", () => {
  it("returns a new array leaving the original order unchanged", () => {
    const rows = [
      makeRow({ run_id: "a", primary_metric: 0.3 }),
      makeRow({ run_id: "b", primary_metric: 0.9 })
    ];
    const original = [...rows];
    sortEvalRows(rows, "primary_metric");
    expect(rows.map((r) => r.run_id)).toEqual(original.map((r) => r.run_id));
  });
});

// ---------------------------------------------------------------------------
// filterEvalRowsByTask
// ---------------------------------------------------------------------------

describe("filterEvalRowsByTask — basic filtering", () => {
  const rows = [
    makeRow({ run_id: "sw-1", task: "swebench_verified" }),
    makeRow({ run_id: "sw-2", task: "swebench_lite" }),
    makeRow({ run_id: "mmlu-1", task: "mmlu" })
  ];

  it("returns only rows whose task contains the filter substring (case-insensitive)", () => {
    const result = filterEvalRowsByTask(rows, "swebench");
    expect(result).toHaveLength(2);
    expect(result.map((r) => r.run_id)).toEqual(["sw-1", "sw-2"]);
  });

  it("is case-insensitive when filtering", () => {
    const result = filterEvalRowsByTask(rows, "SWEBENCH");
    expect(result).toHaveLength(2);
  });

  it("returns empty array when no rows match the filter", () => {
    const result = filterEvalRowsByTask(rows, "unknown-task-xyz");
    expect(result).toEqual([]);
  });
});

describe("filterEvalRowsByTask — passthrough conditions", () => {
  const rows = [makeRow({ run_id: "r1", task: "t1" })];

  it("returns the full list when filter is null", () => {
    expect(filterEvalRowsByTask(rows, null)).toEqual(rows);
  });

  it("returns the full list when filter is an empty string", () => {
    expect(filterEvalRowsByTask(rows, "")).toEqual(rows);
  });

  it("returns the full list when filter is only whitespace", () => {
    expect(filterEvalRowsByTask(rows, "   ")).toEqual(rows);
  });
});

describe("filterEvalRowsByTask — rows with null task", () => {
  it("excludes rows whose task is null when a filter is applied", () => {
    const rows = [makeRow({ run_id: "null-task", task: null }), makeRow({ run_id: "has-task", task: "swebench" })];
    const result = filterEvalRowsByTask(rows, "swebench");
    expect(result).toHaveLength(1);
    expect(result[0]?.run_id).toBe("has-task");
  });
});

// ---------------------------------------------------------------------------
// formatEvalMetric
// ---------------------------------------------------------------------------

describe("formatEvalMetric — representative values", () => {
  it("formats a float to 3 decimal places", () => {
    expect(formatEvalMetric(0.641)).toBe("0.641");
  });

  it("formats an integer without decimal places", () => {
    expect(formatEvalMetric(3)).toBe("3");
  });

  it("formats zero as an integer (no decimals)", () => {
    expect(formatEvalMetric(0)).toBe("0");
  });

  it("formats a negative float to 3 decimal places", () => {
    expect(formatEvalMetric(-0.012)).toBe("-0.012");
  });
});

describe("formatEvalMetric — null/undefined/NaN edge cases", () => {
  it("returns dash for null", () => {
    expect(formatEvalMetric(null)).toBe("—");
  });

  it("returns dash for undefined", () => {
    expect(formatEvalMetric(undefined)).toBe("—");
  });

  it("returns dash for NaN", () => {
    expect(formatEvalMetric(NaN)).toBe("—");
  });
});

// ---------------------------------------------------------------------------
// formatEvalCost
// ---------------------------------------------------------------------------

describe("formatEvalCost — representative values", () => {
  it("formats a cost with $ prefix and 2 decimal places", () => {
    expect(formatEvalCost(7.23)).toBe("$7.23");
  });

  it("formats a zero cost as $0.00", () => {
    expect(formatEvalCost(0)).toBe("$0.00");
  });

  it("formats a fractional cost rounding to 2 decimal places", () => {
    expect(formatEvalCost(12.5)).toBe("$12.50");
  });

  it("formats a large cost correctly", () => {
    expect(formatEvalCost(1000.0)).toBe("$1000.00");
  });
});

describe("formatEvalCost — null/undefined/NaN edge cases", () => {
  it("returns dash for null", () => {
    expect(formatEvalCost(null)).toBe("—");
  });

  it("returns dash for undefined", () => {
    expect(formatEvalCost(undefined)).toBe("—");
  });

  it("returns dash for NaN", () => {
    expect(formatEvalCost(NaN)).toBe("—");
  });
});

// ---------------------------------------------------------------------------
// Type-level structural contract
// ---------------------------------------------------------------------------

describe("EvalLeaderboardData and EvalLogRow structural contract", () => {
  it("EvalLeaderboardData has a rows array (compile-time structural check)", () => {
    const data: EvalLeaderboardData = { rows: [] };
    expect(Array.isArray(data.rows)).toBe(true);
  });

  it("EvalLogRow has all 11 columns at compile time", () => {
    const row: EvalLogRow = {
      run_id: "r",
      task: "t",
      generation: 1,
      primary_metric: 0.5,
      held_out_delta: 0.0,
      model_id: "m",
      prompt_hash: "ph",
      dataset_sha: "ds",
      cost_usd: 1.0,
      git_sha: "gs",
      store_uri: "su"
    };
    expect(Object.keys(row)).toHaveLength(11);
  });

  it("EvalSortKey accepts only the three valid column names", () => {
    const sortKeys: EvalSortKey[] = ["primary_metric", "generation", "cost_usd"];
    // All three are valid; invoking sort with each should not throw
    expect(() => {
      for (const key of sortKeys) {
        sortEvalRows([], key);
      }
    }).not.toThrow();
  });
});
