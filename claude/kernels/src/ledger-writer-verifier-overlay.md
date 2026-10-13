**Verifier ledger rows.** File a row for each per-change debt finding from convention compliance or behavioral-contract compliance: `[DEAD-CODE-UNREMOVED]`, `[BLOAT]`, duplication, function-size and file-size ceiling breaches, nesting-depth violations. Fill every field from the row fields; your values are:
- `source`: verifier. `status`: open. `resolved-by`: empty. `first-seen` and `last-seen`: today.
- `direction`: code-to-goals, or goals-to-code only when the code does not yet meet a stated goal.
- `goal-ref-type`: code-quality (with an empty `goal-ref-value`), or adr, spec-req, architecture or claude-md only when the finding is anchored to a Praxion-native goal.
- `owner-role`: from the owner-role mapping.
- `notes`: one sentence naming the tag or the breached ceiling (for example "function 63 lines, ceiling 50").
- `severity`: critical for a correctness risk or contract violation; important for a quality-ceiling breach or systemic duplication; suggested for surviving overrides and low-impact cleanup.
- `class`: duplication for duplication; complexity for a size or nesting breach; for `[BLOAT]`, complexity, or dead-code when the bloat is a dedicated unused symbol.

When a `[DEAD-CODE-UNREMOVED]` FAIL is overridden by the user or deferred for scope, still file a row, with `severity` suggested, `status` open and a survivor flag in `notes`: survivors persist as tracked debt. One finding yields both a `VERIFICATION_REPORT.md` entry (this review) and a ledger row (persistence beyond the pipeline); never write debt findings into `LEARNINGS.md` or into report sections meant to stand in for the ledger.
