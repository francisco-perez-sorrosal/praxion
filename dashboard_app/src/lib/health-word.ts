import type { HealthLabel } from "@/lib/health-tone";
import { HEALTH_ARROWS } from "@/lib/tone";

/** The glyph that says "no direction" (a first snapshot has nothing to compare). */
const NO_DIRECTION = "·";

/**
 * A health label as the sidebar and the Overview word it: sentence case, then
 * the trend arrow. Word first, arrow second — the arrow never stands alone.
 */
export function healthWord(label: HealthLabel): string {
  const word = `${label.charAt(0)}${label.slice(1).toLowerCase()}`;
  const arrow = HEALTH_ARROWS[label];
  return arrow === NO_DIRECTION ? word : `${word} ${arrow}`;
}
