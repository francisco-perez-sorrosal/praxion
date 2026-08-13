"use client";

import type { ReadinessPillar } from "@/lib/metrics";
import { levelLabel, MAX_LEVEL } from "@/lib/readiness-section-data";

export function LevelTrack({ level, pillars }: { level: number; pillars: ReadinessPillar[] }) {
  const nextIndex = level;
  const blockers =
    level < MAX_LEVEL
      ? pillars.filter((p) => p.level_pass[nextIndex] !== true).map((p) => p.name)
      : [];
  return (
    <div className="readiness-level-track-block">
      <ol className="readiness-level-track" aria-label="Factory readiness level progression">
        {Array.from({ length: MAX_LEVEL }, (_, i) => i + 1).map((lvl) => {
          const state = lvl < level ? "cleared" : lvl === level ? "current" : "pending";
          return (
            <li key={lvl} className="readiness-level-track__step" data-state={state}>
              <span className="readiness-level-track__marker" aria-hidden="true">
                {lvl <= level ? "●" : "○"}
              </span>
              <span className="readiness-level-track__label">{levelLabel(lvl)}</span>
            </li>
          );
        })}
      </ol>
      <p className="readiness-level-track__caption muted">
        {level >= MAX_LEVEL ? (
          <>Top level reached — all pillars clear L{MAX_LEVEL}.</>
        ) : blockers.length > 0 ? (
          <>
            Blocking L{level + 1}: <strong>{blockers.join(", ")}</strong>
          </>
        ) : (
          <>Highest fully-cleared level: {levelLabel(level)}.</>
        )}
      </p>
    </div>
  );
}
