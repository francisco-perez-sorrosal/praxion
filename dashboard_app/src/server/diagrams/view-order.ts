import path from "node:path";

/**
 * Narrative order for rendered diagrams.
 *
 * A LikeC4 model declares its views in the order a reader should meet them, and the
 * regeneration command renders one SVG per view, named after the view id. The dashboard keeps
 * that order: renders are grouped by their `rendered/` directory, ordered within a group by the
 * position of their view among the declarations of the group's `src/*.c4` files, and a render
 * whose view is not declared there follows the declared ones alphabetically.
 */

const VIEW_DECLARATION = /^\s*(?:dynamic\s+|deployment\s+)?view\s+([A-Za-z_][\w-]*)\b/gm;

/** The view ids `source` declares, in declaration order; a repeated id keeps its first place. */
export function declaredViewIds(source: string): string[] {
  const ids: string[] = [];
  for (const match of source.matchAll(VIEW_DECLARATION)) {
    const id = match[1] as string;
    if (!ids.includes(id)) {
      ids.push(id);
    }
  }
  return ids;
}

/**
 * `renderPaths` in narrative order. `declared` maps a `rendered/` directory to the view ids its
 * sibling `src/` declares, in order; a directory it does not name sorts alphabetically.
 */
export function orderRenders(
  renderPaths: readonly string[],
  declared: ReadonlyMap<string, readonly string[]>
): string[] {
  const rank = (renderPath: string): [string, number, string] => {
    const directory = path.dirname(renderPath);
    const stem = path.basename(renderPath, path.extname(renderPath));
    const position = (declared.get(directory) ?? []).indexOf(stem);
    return [directory, position >= 0 ? position : Number.MAX_SAFE_INTEGER, stem];
  };
  return [...renderPaths].sort((left, right) => {
    const [leftDir, leftPosition, leftStem] = rank(left);
    const [rightDir, rightPosition, rightStem] = rank(right);
    if (leftDir !== rightDir) {
      return leftDir.localeCompare(rightDir);
    }
    if (leftPosition !== rightPosition) {
      return leftPosition - rightPosition;
    }
    return leftStem.localeCompare(rightStem);
  });
}
