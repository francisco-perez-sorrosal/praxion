import { describe, expect, it } from "vitest";

import { buildAdrGraph } from "@/server/view-models/adr-graph";
import {
  assignCoordinates,
  computeLayers
} from "@/components/viz/decision-graph";

// ─── buildAdrGraph tests ──────────────────────────────────────────────────────

describe("buildAdrGraph", () => {
  it("keeps every target when one decision supersedes several", () => {
    // The scalar form under-recorded 2 of dec-225's 3 backward edges: it
    // replaced three memory decisions and the graph drew one.
    const graph = buildAdrGraph([
      {
        data: {
          id: "dec-225",
          title: "Remove the in-house memory subsystem",
          status: "accepted",
          supersedes: ["dec-009", "dec-025", "dec-039"]
        },
        slug: "225-remove-memory"
      }
    ]);

    expect(graph[0]?.supersedes).toEqual(["dec-009", "dec-025", "dec-039"]);
  });

  it("extracts supersedes and re_affirms links from a 3-ADR fixture", () => {
    const records = [
      {
        data: {
          id: "dec-003",
          title: "New runtime decision",
          status: "accepted",
          supersedes: "dec-002"
        },
        slug: "003-new-runtime"
      },
      {
        data: {
          id: "dec-002",
          title: "Old runtime decision",
          status: "superseded",
          superseded_by: "dec-003"
        },
        slug: "002-old-runtime"
      },
      {
        data: {
          id: "dec-004",
          title: "Re-affirmation decision",
          status: "re-affirmation",
          re_affirms: "dec-003"
        },
        slug: "004-reaffirm"
      }
    ];

    const graph = buildAdrGraph(records);

    expect(graph).toHaveLength(3);

    const node003 = graph.find((n) => n.id === "dec-003");
    expect(node003?.supersedes).toEqual(["dec-002"]);
    expect(node003?.title).toBe("New runtime decision");
    expect(node003?.status).toBe("accepted");

    const node002 = graph.find((n) => n.id === "dec-002");
    expect(node002?.superseded_by).toBe("dec-003");

    const node004 = graph.find((n) => n.id === "dec-004");
    expect(node004?.re_affirms).toBe("dec-003");
  });

  it("preserves re_affirmed_by array from frontmatter", () => {
    const records = [
      {
        data: {
          id: "dec-001",
          title: "Original decision",
          status: "accepted",
          re_affirmed_by: ["dec-005", "dec-007"]
        },
        slug: "001-original"
      }
    ];

    const graph = buildAdrGraph(records);

    const node = graph.find((n) => n.id === "dec-001");
    expect(node?.re_affirmed_by).toEqual(["dec-005", "dec-007"]);
  });

  it("returns nodes with no edge fields when frontmatter has no relationship fields", () => {
    const records = [
      {
        data: { id: "dec-010", title: "Standalone", status: "accepted" },
        slug: "010-standalone"
      },
      {
        data: { id: "dec-011", title: "Also standalone", status: "proposed" },
        slug: "011-also-standalone"
      }
    ];

    const graph = buildAdrGraph(records);

    expect(graph).toHaveLength(2);
    for (const node of graph) {
      expect(node.supersedes).toBeUndefined();
      expect(node.superseded_by).toBeUndefined();
      expect(node.re_affirms).toBeUndefined();
      expect(node.re_affirmed_by).toBeUndefined();
    }
  });

  it("does not crash on missing or undefined frontmatter fields", () => {
    const records = [
      { data: {}, slug: "no-fields" },
      { data: { id: "dec-020" }, slug: "only-id" },
      { data: { title: "Only title" }, slug: "only-title" }
    ];

    expect(() => buildAdrGraph(records)).not.toThrow();

    const graph = buildAdrGraph(records);
    expect(graph).toHaveLength(3);
    // All should have valid id, title, status
    for (const node of graph) {
      expect(typeof node.id).toBe("string");
      expect(typeof node.title).toBe("string");
      expect(typeof node.status).toBe("string");
    }
  });

  it("uses slug as fallback id when frontmatter has no id field", () => {
    const records = [
      { data: { title: "Slug fallback", status: "accepted" }, slug: "042-slug-fallback" }
    ];

    const graph = buildAdrGraph(records);
    expect(graph[0]?.id).toBe("042-slug-fallback");
  });

  it("handles 50+ nodes without error and returns correct count", () => {
    const records = Array.from({ length: 60 }, (_, i) => ({
      data: {
        id: `dec-${String(i + 1).padStart(3, "0")}`,
        title: `Decision ${i + 1}`,
        status: i % 2 === 0 ? "accepted" : "proposed"
      },
      slug: `${String(i + 1).padStart(3, "0")}-decision-${i + 1}`
    }));

    const graph = buildAdrGraph(records);
    expect(graph).toHaveLength(60);
  });

  it("handles dec-draft-<hash> id forms without normalization", () => {
    const records = [
      {
        data: {
          id: "dec-draft-a1b2c3d4", // id-citation-discipline:ignore
          title: "Draft decision",
          status: "proposed",
          supersedes: "dec-draft-e5f6a7b8" // id-citation-discipline:ignore
        },
        slug: "draft-slug"
      }
    ];

    const graph = buildAdrGraph(records);
    expect(graph[0]?.id).toBe("dec-draft-a1b2c3d4"); // id-citation-discipline:ignore
    expect(graph[0]?.supersedes).toEqual(["dec-draft-e5f6a7b8"]); // id-citation-discipline:ignore
  });

  it("renders every edge of a record carrying all three narrowing/retirement fields at once", () => {
    // dec-347's own bug class: a family added but silently dropped by the
    // renderer is worse than never having the data, because the graph then
    // asserts "no relation" where one exists. Assert exact edge values, not
    // mere presence, so a partially-wired field cannot pass this test.
    const graph = buildAdrGraph([
      {
        data: {
          id: "dec-263",
          title: "Narrows and retires several decisions",
          status: "accepted",
          supersedes_in_part: ["dec-219"],
          superseded_in_part_by: ["dec-400"],
          retired_by: ["dec-401", "dec-402"]
        },
        slug: "263-narrows-and-retires"
      }
    ]);

    const node = graph[0];
    expect(node?.supersedes_in_part).toEqual(["dec-219"]);
    expect(node?.superseded_in_part_by).toEqual(["dec-400"]);
    expect(node?.retired_by).toEqual(["dec-401", "dec-402"]);
  });

  it("coerces a scalar supersedes_in_part into a single-element list", () => {
    const graph = buildAdrGraph([
      {
        data: {
          id: "dec-500",
          title: "Narrows one decision",
          status: "accepted",
          supersedes_in_part: "dec-100"
        },
        slug: "500-narrows-one"
      }
    ]);

    expect(graph[0]?.supersedes_in_part).toEqual(["dec-100"]);
  });

  it("coerces a scalar superseded_in_part_by into a single-element list", () => {
    const graph = buildAdrGraph([
      {
        data: {
          id: "dec-100",
          title: "Narrowed by dec-500",
          status: "accepted",
          superseded_in_part_by: "dec-500"
        },
        slug: "100-narrowed"
      }
    ]);

    expect(graph[0]?.superseded_in_part_by).toEqual(["dec-500"]);
  });

  it("coerces a scalar retired_by into a single-element list", () => {
    // The pre-existing omission this step closes: retired_by never reached
    // the graph at all, scalar or list.
    const graph = buildAdrGraph([
      {
        data: {
          id: "dec-600",
          title: "Retired by one decision",
          status: "retired",
          retired_by: "dec-601"
        },
        slug: "600-retired"
      }
    ]);

    expect(graph[0]?.retired_by).toEqual(["dec-601"]);
  });

  it("omits supersedes_in_part, superseded_in_part_by, and retired_by keys when frontmatter carries none of them", () => {
    const graph = buildAdrGraph([
      {
        data: { id: "dec-700", title: "No narrowing or retirement", status: "accepted" },
        slug: "700-plain"
      }
    ]);

    const node = graph[0];
    expect(node?.supersedes_in_part).toBeUndefined();
    expect(node?.superseded_in_part_by).toBeUndefined();
    expect(node?.retired_by).toBeUndefined();
    expect(Object.prototype.hasOwnProperty.call(node, "supersedes_in_part")).toBe(false);
    expect(Object.prototype.hasOwnProperty.call(node, "superseded_in_part_by")).toBe(false);
    expect(Object.prototype.hasOwnProperty.call(node, "retired_by")).toBe(false);
  });
});

// ─── computeLayers tests ──────────────────────────────────────────────────────

describe("computeLayers (longest-path layering)", () => {
  it("assigns layer 0 to all nodes when no supersedes links", () => {
    const nodes = [
      { id: "a", title: "A", status: "accepted" },
      { id: "b", title: "B", status: "proposed" }
    ];

    const layers = computeLayers(nodes);
    expect(layers.get("a")).toBe(0);
    expect(layers.get("b")).toBe(0);
  });

  it("places the superseded node one layer deeper than its superseder", () => {
    // dec-003 supersedes dec-002 → dec-002 should be at layer 1
    const nodes = [
      { id: "dec-003", title: "New", status: "accepted", supersedes: ["dec-002"] },
      { id: "dec-002", title: "Old", status: "superseded" }
    ];

    const layers = computeLayers(nodes);
    expect(layers.get("dec-003")).toBe(0);
    expect(layers.get("dec-002")).toBe(1);
  });

  it("computes depth correctly for a chain of length 3", () => {
    const nodes = [
      { id: "c", title: "Newest", status: "accepted", supersedes: ["b"] },
      { id: "b", title: "Middle", status: "superseded", supersedes: ["a"] },
      { id: "a", title: "Oldest", status: "superseded" }
    ];

    const layers = computeLayers(nodes);
    expect(layers.get("c")).toBe(0);
    expect(layers.get("b")).toBe(1);
    expect(layers.get("a")).toBe(2);
  });

  it("ignores supersedes references to ids not in the node list", () => {
    const nodes = [
      { id: "x", title: "External ref", status: "accepted", supersedes: ["dec-external"] }
    ];

    const layers = computeLayers(nodes);
    expect(layers.get("x")).toBe(0);
  });
});

// ─── assignCoordinates tests ──────────────────────────────────────────────────

describe("assignCoordinates", () => {
  it("assigns distinct x positions to sibling nodes in the same layer", () => {
    const nodes = [
      { id: "a", title: "A", status: "accepted" },
      { id: "b", title: "B", status: "proposed" }
    ];
    const layers = computeLayers(nodes);
    const layout = assignCoordinates(nodes, layers);

    const posA = layout.nodes.find((n) => n.id === "a");
    const posB = layout.nodes.find((n) => n.id === "b");

    expect(posA).toBeDefined();
    expect(posB).toBeDefined();
    if (posA && posB) {
      expect(posA.x).not.toBe(posB.x);
      expect(posA.y).toBe(posB.y);
    }
  });

  it("assigns different y positions to nodes in different layers", () => {
    const nodes = [
      { id: "newer", title: "Newer", status: "accepted", supersedes: ["older"] },
      { id: "older", title: "Older", status: "superseded" }
    ];
    const layers = computeLayers(nodes);
    const layout = assignCoordinates(nodes, layers);

    const posNewer = layout.nodes.find((n) => n.id === "newer");
    const posOlder = layout.nodes.find((n) => n.id === "older");

    expect(posNewer).toBeDefined();
    expect(posOlder).toBeDefined();
    if (posNewer && posOlder) {
      expect(posNewer.y).not.toBe(posOlder.y);
    }
  });

  it("returns positive width and height", () => {
    const nodes = [{ id: "a", title: "A", status: "accepted" }];
    const layers = computeLayers(nodes);
    const layout = assignCoordinates(nodes, layers);

    expect(layout.width).toBeGreaterThan(0);
    expect(layout.height).toBeGreaterThan(0);
  });
});
