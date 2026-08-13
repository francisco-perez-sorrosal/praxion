"use client";

import { EducationalPopover } from "@/components/educational-popover";
import { READINESS_DOCS, type ReadinessDocKey } from "@/lib/readiness-docs";
import type { ReadinessPillar } from "@/lib/metrics";

/** A `?` popover carrying instrument-level documentation for a concept. */
export function DocInfo({ docKey }: { docKey: ReadinessDocKey }) {
  const doc = READINESS_DOCS[docKey];
  return <EducationalPopover title={doc.title} body={doc.body} />;
}

/** A section subheading paired with its educational popover. */
export function Subhead({
  text,
  docKey,
  minor = false
}: {
  text: string;
  docKey: ReadinessDocKey;
  minor?: boolean;
}) {
  const Tag = minor ? "h5" : "h4";
  return (
    <Tag className={`readiness-subhead${minor ? " readiness-subhead--minor" : ""}`}>
      <span className="readiness-subhead__text">{text}</span>
      <DocInfo docKey={docKey} />
    </Tag>
  );
}

/** A small marker showing a pillar's weight when it differs from the default 1. */
export function PillarWeightMarker({ pillar }: { pillar: ReadinessPillar }) {
  if (pillar.excluded) {
    return (
      <span className="readiness-pillar-weight" data-excluded="true" title="Excluded from the adjusted score (weight 0)">
        excluded
      </span>
    );
  }
  if (typeof pillar.weight === "number" && pillar.weight !== 1) {
    return (
      <span className="readiness-pillar-weight" title={`Counts ×${pillar.weight} in the adjusted score`}>
        ×{pillar.weight}
      </span>
    );
  }
  return null;
}
