"use client";

export type CollectorEntry = {
  tool: string;
  status: string;
  version: string | null;
  reason: string | null;
  hint: string | null;
};

const DEGRADED_STATUSES = new Set(["unavailable", "error", "timeout"]);

function collectorIcon(status: string): string {
  if (status === "available") return "✓";
  if (DEGRADED_STATUSES.has(status)) return "✕";
  return "⚠";
}

export function CollectorChips({ collectors }: { collectors: CollectorEntry[] }) {
  if (collectors.length === 0) {
    return <p className="muted">No collector metadata exists in this snapshot.</p>;
  }

  return (
    <ul className="collector-chips">
      {collectors.map(({ tool, status, version, reason, hint }) => {
        const isDegraded = DEGRADED_STATUSES.has(status);
        const detail = version ?? reason ?? hint ?? status;
        return (
          <li
            key={tool}
            className={`collector-chip${isDegraded ? " collector-chip--degraded" : ""}`}
          >
            <span className="collector-chip__icon" aria-hidden="true">
              {collectorIcon(status)}
            </span>
            <span className="collector-chip__name">{tool}</span>
            <span className="collector-chip__detail">{detail}</span>
          </li>
        );
      })}
    </ul>
  );
}
