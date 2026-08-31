import "server-only";

import type { MarkdownFile } from "@/server/types";

// ─── Types ────────────────────────────────────────────────────────────────────

export type AdrGraphNode = {
  readonly id: string;
  readonly title: string;
  readonly status: string;
  readonly supersedes?: readonly string[];
  readonly superseded_by?: string;
  readonly re_affirms?: string;
  readonly re_affirmed_by?: string[];
  readonly supersedes_in_part?: readonly string[];
  readonly superseded_in_part_by?: readonly string[];
  readonly retired_by?: readonly string[];
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

type AdrRecord = Pick<MarkdownFile, "data"> & { slug?: string };

function asString(value: unknown): string | undefined {
  return typeof value === "string" && value.length > 0 ? value : undefined;
}

function asStringArray(value: unknown): string[] | undefined {
  if (!Array.isArray(value)) return undefined;
  const filtered = value.filter((v): v is string => typeof v === "string");
  return filtered.length > 0 ? filtered : undefined;
}

/**
 * Normalizes a scalar-or-list id field to a list.
 *
 * `supersedes` is typed `string | list`: one decision commonly replaces
 * several, and a scalar cannot say so. Reading it with `asString` silently
 * dropped every edge of a multi-target supersession — the graph rendered
 * dec-225 as replacing one decision when it replaced three.
 */
function asIdList(value: unknown): string[] | undefined {
  const single = asString(value);
  if (single !== undefined) return [single];
  return asStringArray(value);
}

function resolveId(data: Record<string, unknown>, slug: string | undefined): string {
  // Prefer the explicit id field from frontmatter
  const idField = asString(data["id"]);
  if (idField !== undefined) return idField;
  // Fall back to slug (filename without extension)
  return slug ?? "unknown";
}

// ─── Public API ───────────────────────────────────────────────────────────────

/**
 * Builds a flat array of AdrGraphNode from already-loaded ADR records.
 *
 * Reads frontmatter fields: id, title, status, supersedes, superseded_by,
 * re_affirms, re_affirmed_by, supersedes_in_part, superseded_in_part_by,
 * retired_by. Works for both dec-NNN and dec-draft-<hash> ids. Records
 * missing required fields are included with sensible defaults (not
 * omitted) so the graph remains consistent.
 */
export function buildAdrGraph(adrs: AdrRecord[]): AdrGraphNode[] {
  return adrs.map((record) => {
    const { data, slug } = record;
    const id = resolveId(data, slug);
    const title = asString(data["title"]) ?? id;
    const status = asString(data["status"]) ?? "proposed";
    const supersedes = asIdList(data["supersedes"]);
    const superseded_by = asString(data["superseded_by"]);
    const re_affirms = asString(data["re_affirms"]);
    const re_affirmed_by = asStringArray(data["re_affirmed_by"]);
    const supersedes_in_part = asIdList(data["supersedes_in_part"]);
    const superseded_in_part_by = asIdList(data["superseded_in_part_by"]);
    const retired_by = asIdList(data["retired_by"]);

    return {
      id,
      title,
      status,
      ...(supersedes !== undefined && { supersedes }),
      ...(superseded_by !== undefined && { superseded_by }),
      ...(re_affirms !== undefined && { re_affirms }),
      ...(re_affirmed_by !== undefined && { re_affirmed_by }),
      ...(supersedes_in_part !== undefined && { supersedes_in_part }),
      ...(superseded_in_part_by !== undefined && { superseded_in_part_by }),
      ...(retired_by !== undefined && { retired_by })
    };
  });
}
