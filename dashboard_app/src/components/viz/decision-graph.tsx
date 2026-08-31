"use client";

import { useMemo } from "react";

import { usePanZoom } from "./use-pan-zoom";
import type { AdrGraphNode } from "@/server/view-models/adr-graph";

// ─── Layout constants ─────────────────────────────────────────────────────────

const NODE_RADIUS = 20;
const LAYER_HEIGHT = 100;
const NODE_SPACING = 60;
const GRAPH_PADDING = 40;
const LABEL_MAX_CHARS = 22;
const SVG_MIN_WIDTH = 400;
const SVG_MIN_HEIGHT = 200;

// ─── Types ────────────────────────────────────────────────────────────────────

type LayeredNode = AdrGraphNode & {
  readonly layer: number;
  readonly x: number;
  readonly y: number;
};

type GraphLayout = {
  readonly nodes: LayeredNode[];
  readonly width: number;
  readonly height: number;
};

type EdgeKind = "supersedes" | "supersedes_in_part" | "re_affirms" | "retired_by";

type GraphEdge = {
  readonly sourceId: string;
  readonly targetId: string;
  readonly kind: EdgeKind;
};

// Distinct dash pattern per edge kind, in the same visual vocabulary as the
// existing solid/dashed split — each kind must stay visually distinguishable
// from its neighbors without relying on color.
const EDGE_DASH_PATTERN: Record<EdgeKind, string | undefined> = {
  supersedes: undefined,
  supersedes_in_part: "2 3",
  re_affirms: "5 4",
  retired_by: "1 3"
};

// ─── Props ────────────────────────────────────────────────────────────────────

type DecisionGraphProps = {
  readonly nodes: AdrGraphNode[];
  readonly onSelect?: (id: string) => void;
  readonly minZoom?: number;
  readonly maxZoom?: number;
};

// ─── Pure layout helpers (exported for testing) ──────────────────────────────

/**
 * Computes the longest-path layer for each node.
 * Layer 0 = nodes with no predecessors (roots).
 * Layer N = max(layer of predecessors) + 1.
 */
export function computeLayers(nodes: AdrGraphNode[]): Map<string, number> {
  const layers = new Map<string, number>();
  const idSet = new Set(nodes.map((n) => n.id));

  // BFS-based longest path: iterate until stable
  for (const node of nodes) {
    layers.set(node.id, 0);
  }

  let changed = true;
  let maxIter = nodes.length + 1;
  while (changed && maxIter-- > 0) {
    changed = false;
    for (const node of nodes) {
      const nodeLayer = layers.get(node.id) ?? 0;
      for (const target of node.supersedes ?? []) {
        if (!idSet.has(target)) continue;
        const targetLayer = layers.get(target) ?? 0;
        const desired = nodeLayer + 1;
        if (desired > targetLayer) {
          layers.set(target, desired);
          changed = true;
        }
      }
    }
  }

  return layers;
}

/**
 * Assigns x/y coordinates given layers.
 * Nodes in the same layer are spread evenly horizontally.
 */
export function assignCoordinates(
  nodes: AdrGraphNode[],
  layers: Map<string, number>
): GraphLayout {
  // Group nodes by layer
  const byLayer = new Map<number, AdrGraphNode[]>();
  for (const node of nodes) {
    const layer = layers.get(node.id) ?? 0;
    const group = byLayer.get(layer) ?? [];
    group.push(node);
    byLayer.set(layer, group);
  }

  const maxLayer = byLayer.size > 0 ? Math.max(...byLayer.keys()) : 0;
  const maxPerLayer = Math.max(...Array.from(byLayer.values()).map((g) => g.length), 1);

  const contentWidth = Math.max(
    SVG_MIN_WIDTH,
    maxPerLayer * (NODE_RADIUS * 2 + NODE_SPACING) + GRAPH_PADDING * 2
  );
  const contentHeight = Math.max(
    SVG_MIN_HEIGHT,
    (maxLayer + 1) * LAYER_HEIGHT + GRAPH_PADDING * 2
  );

  const layeredNodes: LayeredNode[] = [];
  for (const [layer, group] of byLayer.entries()) {
    const y = GRAPH_PADDING + layer * LAYER_HEIGHT + NODE_RADIUS;
    const totalW = group.length * (NODE_RADIUS * 2 + NODE_SPACING) - NODE_SPACING;
    const startX = (contentWidth - totalW) / 2 + NODE_RADIUS;
    for (let i = 0; i < group.length; i++) {
      const node = group[i];
      if (node === undefined) continue;
      const x = startX + i * (NODE_RADIUS * 2 + NODE_SPACING);
      layeredNodes.push({ ...node, layer, x, y });
    }
  }

  return { nodes: layeredNodes, width: contentWidth, height: contentHeight };
}

// ─── Edge extraction ──────────────────────────────────────────────────────────

function extractEdges(nodes: AdrGraphNode[]): GraphEdge[] {
  const idSet = new Set(nodes.map((n) => n.id));
  const edges: GraphEdge[] = [];

  for (const node of nodes) {
    for (const target of node.supersedes ?? []) {
      if (idSet.has(target)) {
        edges.push({ sourceId: node.id, targetId: target, kind: "supersedes" });
      }
    }
    // Read only the forward field (supersedes_in_part), mirroring the
    // supersedes/superseded_by pair above: reciprocity is enforced upstream
    // (status_edge_conflicts), so reading both directions would double-draw
    // the same edge.
    for (const target of node.supersedes_in_part ?? []) {
      if (idSet.has(target)) {
        edges.push({ sourceId: node.id, targetId: target, kind: "supersedes_in_part" });
      }
    }
    if (node.re_affirms && idSet.has(node.re_affirms)) {
      edges.push({ sourceId: node.id, targetId: node.re_affirms, kind: "re_affirms" });
    }
    for (const target of node.retired_by ?? []) {
      if (idSet.has(target)) {
        edges.push({ sourceId: node.id, targetId: target, kind: "retired_by" });
      }
    }
  }

  return edges;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function truncateLabel(title: string): string {
  return title.length <= LABEL_MAX_CHARS ? title : `${title.slice(0, LABEL_MAX_CHARS - 1)}…`;
}

function statusToVar(status: string): string {
  const normalized = status.toLowerCase().replace(/[-_\s]/g, "");
  const knownStatuses: Record<string, string> = {
    accepted: "var(--status-accepted)",
    superseded: "var(--status-superseded)",
    proposed: "var(--status-proposed)",
    reaffirmation: "var(--status-reaffirmation)"
  };
  return knownStatuses[normalized] ?? "var(--color-border)";
}

function hasAnyEdge(node: AdrGraphNode): boolean {
  return (
    (node.supersedes !== undefined && node.supersedes.length > 0) ||
    node.superseded_by !== undefined ||
    node.re_affirms !== undefined ||
    (node.re_affirmed_by !== undefined && node.re_affirmed_by.length > 0) ||
    (node.supersedes_in_part !== undefined && node.supersedes_in_part.length > 0) ||
    (node.superseded_in_part_by !== undefined && node.superseded_in_part_by.length > 0) ||
    (node.retired_by !== undefined && node.retired_by.length > 0)
  );
}

// ─── Degenerate legend (no edges) ────────────────────────────────────────────

function StandaloneDecisionsLegend({ count }: { readonly count: number }) {
  return (
    <div className="decision-graph-legend">
      <p className="decision-graph-legend-note">+{count} standalone decisions (no links)</p>
      <ul className="decision-graph-legend-list">
        {(["accepted", "superseded", "proposed", "reaffirmation"] as const).map((status) => (
          <li key={status} className="decision-graph-legend-item">
            <svg width={16} height={16} aria-hidden="true">
              <circle cx={8} cy={8} r={6} fill={statusToVar(status)} />
            </svg>
            <span>{status}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

export function DecisionGraph({
  nodes,
  onSelect,
  minZoom,
  maxZoom
}: DecisionGraphProps) {
  const nodesWithEdges = useMemo(
    () => nodes.filter(hasAnyEdge),
    [nodes]
  );

  // Degenerate case: no supersession/re-affirmation edges at all
  if (nodesWithEdges.length === 0) {
    return <StandaloneDecisionsLegend count={nodes.length} />;
  }

  return <DecisionGraphInner nodes={nodes} onSelect={onSelect} minZoom={minZoom} maxZoom={maxZoom} />;
}

// ─── Inner graph renderer (only shown when edges exist) ──────────────────────

function DecisionGraphInner({
  nodes,
  onSelect,
  minZoom,
  maxZoom
}: DecisionGraphProps) {
  const layout = useMemo<GraphLayout>(() => {
    const layers = computeLayers(nodes);
    return assignCoordinates(nodes, layers);
  }, [nodes]);

  const edges = useMemo(() => extractEdges(nodes), [nodes]);

  const {
    containerRef,
    transform,
    onWheel,
    onPointerDown,
    onPointerMove,
    onPointerUp,
    onKeyDown,
    reset
  } = usePanZoom({ minZoom, maxZoom });

  const transformStyle = `translate(${transform.x}px, ${transform.y}px) scale(${transform.scale})`;
  const posMap = new Map(layout.nodes.map((n) => [n.id, { x: n.x, y: n.y }]));

  return (
    <div className="decision-graph-root">
      <div
        ref={containerRef}
        className="decision-graph-viewport"
        role="region"
        aria-label="ADR relationship graph"
        tabIndex={0}
        onWheel={onWheel}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onKeyDown={onKeyDown}
      >
        <div
          data-pan-zoom-content
          style={{ transform: transformStyle, transformOrigin: "0 0" }}
        >
          <svg
            width={layout.width}
            height={layout.height}
            viewBox={`0 0 ${layout.width} ${layout.height}`}
            aria-label="ADR relationship graph"
          >
            {/* Edges */}
            <g>
              {edges.map((edge) => {
                const src = posMap.get(edge.sourceId);
                const tgt = posMap.get(edge.targetId);
                if (!src || !tgt) return null;
                return (
                  <line
                    key={`${edge.sourceId}-${edge.targetId}-${edge.kind}`}
                    x1={src.x}
                    y1={src.y}
                    x2={tgt.x}
                    y2={tgt.y}
                    stroke="var(--color-text-muted)"
                    strokeWidth={1.5}
                    strokeDasharray={EDGE_DASH_PATTERN[edge.kind]}
                  />
                );
              })}
            </g>
            {/* Nodes */}
            <g>
              {layout.nodes.map((node) => (
                <g
                  key={node.id}
                  transform={`translate(${node.x}, ${node.y})`}
                  style={{ cursor: onSelect ? "pointer" : "default" }}
                  onClick={() => onSelect?.(node.id)}
                  role={onSelect ? "button" : undefined}
                  aria-label={node.title}
                  tabIndex={onSelect ? 0 : undefined}
                  onKeyDown={(e) => {
                    if (onSelect && (e.key === "Enter" || e.key === " ")) {
                      e.preventDefault();
                      onSelect(node.id);
                    }
                  }}
                >
                  <circle
                    r={NODE_RADIUS}
                    fill={statusToVar(node.status)}
                    stroke="var(--color-border)"
                    strokeWidth={1}
                  />
                  <title>{node.title}</title>
                  <text
                    textAnchor="middle"
                    dominantBaseline="middle"
                    dy={NODE_RADIUS + 12}
                    fontSize="10"
                    fill="var(--color-text-muted)"
                  >
                    {truncateLabel(node.title)}
                  </text>
                </g>
              ))}
            </g>
          </svg>
        </div>
      </div>
      <div className="decision-graph-controls">
        <button
          type="button"
          className="decision-graph-reset"
          aria-label="Reset graph to fit"
          onClick={reset}
        >
          Reset
        </button>
      </div>
    </div>
  );
}
