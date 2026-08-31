// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { DecisionGraph } from "@/components/viz/decision-graph";
import type { AdrGraphNode } from "@/server/view-models/adr-graph";

// jsdom has no ResizeObserver or pointer-capture. The interactive graph
// branch (nodes with edges) mounts usePanZoom, which needs both at click
// time — the degenerate (no-edges) branch below does not (see LEARNINGS.md).
class FakeResizeObserver {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}

beforeEach(() => {
  global.ResizeObserver = FakeResizeObserver;
  if (!HTMLElement.prototype.setPointerCapture) {
    HTMLElement.prototype.setPointerCapture = () => {};
  }
  if (!HTMLElement.prototype.releasePointerCapture) {
    HTMLElement.prototype.releasePointerCapture = () => {};
  }
});

afterEach(() => {
  cleanup();
  // @ts-expect-error -- undo the polyfill so it does not leak into other files
  delete global.ResizeObserver;
});

function twoLinkedNodes(): AdrGraphNode[] {
  return [
    { id: "dec-001", title: "Use Postgres", status: "accepted" },
    {
      id: "dec-002",
      title: "Replace Postgres with SQLite",
      status: "accepted",
      supersedes: ["dec-001"]
    }
  ];
}

describe("DecisionGraph — clicking a node reports the selection", () => {
  it("invokes onSelect exactly once with the clicked node's id", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(<DecisionGraph nodes={twoLinkedNodes()} onSelect={onSelect} />);

    await user.click(screen.getByRole("button", { name: "Use Postgres" }));

    expect(onSelect).toHaveBeenCalledWith("dec-001");
    expect(onSelect).toHaveBeenCalledTimes(1);
  });
});

describe("DecisionGraph — degenerate case: no supersession/re-affirmation edges", () => {
  it("renders the standalone-decisions legend instead of the interactive graph", () => {
    const nodes: AdrGraphNode[] = [{ id: "dec-001", title: "Use Postgres", status: "accepted" }];
    const { container } = render(<DecisionGraph nodes={nodes} />);

    expect(container.querySelector(".decision-graph-legend")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /reset/i })).toBeNull();
  });
});

describe("DecisionGraph — partial-supersession edges", () => {
  it("draws an edge for a node whose only relation is supersedes_in_part", () => {
    const nodes: AdrGraphNode[] = [
      { id: "dec-040", title: "Old broad decision", status: "accepted" },
      {
        id: "dec-204",
        title: "Narrows the old decision",
        status: "accepted",
        supersedes_in_part: ["dec-040"]
      }
    ];
    const { container } = render(<DecisionGraph nodes={nodes} />);

    // A fixture node with only a partial edge must not fall into the
    // standalone-decisions legend, and must produce a drawn <line>.
    expect(container.querySelector(".decision-graph-legend")).toBeNull();
    expect(container.querySelectorAll("svg > g > line")).toHaveLength(1);
  });

  it("draws an edge for a node whose only relation is retired_by", () => {
    const nodes: AdrGraphNode[] = [
      { id: "dec-050", title: "Retiring decision", status: "accepted" },
      {
        id: "dec-010",
        title: "Retired decision",
        status: "accepted",
        retired_by: ["dec-050"]
      }
    ];
    const { container } = render(<DecisionGraph nodes={nodes} />);

    expect(container.querySelector(".decision-graph-legend")).toBeNull();
    expect(container.querySelectorAll("svg > g > line")).toHaveLength(1);
  });

  it("draws every edge kind present without dropping any", () => {
    const nodes: AdrGraphNode[] = [
      { id: "dec-001", title: "Base decision", status: "accepted" },
      { id: "dec-002", title: "Full supersession", status: "accepted", supersedes: ["dec-001"] },
      {
        id: "dec-003",
        title: "Partial supersession",
        status: "accepted",
        supersedes_in_part: ["dec-001"]
      },
      { id: "dec-004", title: "Re-affirmation", status: "re-affirmation", re_affirms: "dec-001" },
      { id: "dec-005", title: "Retired sibling", status: "accepted", retired_by: ["dec-002"] }
    ];
    const { container } = render(<DecisionGraph nodes={nodes} />);

    expect(container.querySelectorAll("svg > g > line")).toHaveLength(4);
  });
});
