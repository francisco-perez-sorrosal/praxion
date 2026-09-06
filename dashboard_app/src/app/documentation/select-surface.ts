import type { ManifestSurface } from "@/server/types";

type SearchParams = Record<string, string | string[] | undefined>;

/**
 * Pick the surface a documentation request refers to.
 *
 * `?surface=<id>` wins when it names a known surface; anything else — absent,
 * repeated (an array), or an unknown id — falls back to the first surface in
 * the manifest, and to `null` when the manifest lists none. Pure: no I/O, no
 * React, unit-testable on its own.
 */
export function selectSurface(
  surfaces: readonly ManifestSurface[],
  params: SearchParams
): ManifestSurface | null {
  const requestedId = typeof params.surface === "string" ? params.surface : null;
  return surfaces.find((surface) => surface.id === requestedId) ?? surfaces[0] ?? null;
}
