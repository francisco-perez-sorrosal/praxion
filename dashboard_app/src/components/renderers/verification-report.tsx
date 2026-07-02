import { MarkdownSurface } from "@/components/markdown-surface";
import { DefaultShell } from "@/components/shells";
import type { ManifestSurface } from "@/server/types";

type RendererProps = {
  readonly body: string;
  readonly surface?: ManifestSurface;
};

const VERDICT_RE = /\b(PASS|FAIL|WARN)\b/;

function extractVerdict(body: string): string | null {
  const match = VERDICT_RE.exec(body);
  return match === null ? null : (match[1] ?? null);
}

/**
 * Surfaces the report's overall PASS/FAIL/WARN verdict as visible badge
 * text (never color alone — WCAG non-text contrast) above the full body.
 */
export function VerificationReportRenderer({ body }: RendererProps) {
  const verdict = extractVerdict(body);
  if (verdict === null) {
    return <DefaultShell body={body} />;
  }

  return (
    <div className="renderer-verification">
      <p className="renderer-verification-heading">
        Verification report
        <span className="renderer-verification-verdict" data-verdict={verdict.toLowerCase()}>
          {verdict}
        </span>
      </p>
      <div className="renderer-verification-body">
        <MarkdownSurface body={body} />
      </div>
    </div>
  );
}
