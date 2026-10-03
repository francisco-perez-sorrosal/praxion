import { TonePill } from "@/components/chrome/tone-pill";
import type { PraxionEvalCheckGroup } from "@/lib/praxion-evals";
import type { Tone } from "@/lib/tone";

type CheckGroupsProps = {
  groups: readonly PraxionEvalCheckGroup[];
  /** Failures name the artifacts that failed; warnings are counts only. */
  showArtifacts: boolean;
  tone: Tone;
};

/**
 * Checks grouped by name, largest group first: the check, its count as a toned
 * pill ("×2" reads without colour), and optionally the artifacts it names.
 */
export function CheckGroups({ groups, showArtifacts, tone }: CheckGroupsProps) {
  return (
    <ul className="eval-groups">
      {groups.map((group) => (
        <li className="eval-group" key={group.check}>
          <div className="eval-group__head">
            <code className="eval-group__check">{group.check}</code>
            <TonePill mono tone={tone}>
              ×{group.count}
            </TonePill>
          </div>
          {showArtifacts && group.artifacts.length > 0 ? (
            <ul className="eval-group__artifacts">
              {group.artifacts.map((artifact) => (
                <li key={artifact}>
                  <code>{artifact}</code>
                </li>
              ))}
            </ul>
          ) : null}
        </li>
      ))}
    </ul>
  );
}
