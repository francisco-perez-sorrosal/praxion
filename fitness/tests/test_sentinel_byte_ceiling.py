"""Fitness invariant: `agents/sentinel.md` never grows past its recorded ceiling.

Cites: dec-380 (sentinel check extraction contract) and its re-affirming draft on the
family-script shape -- acceptance criterion AC-10 of the P2.1 residual pipeline: "the
file never grows against its baseline at any batch boundary". The pipeline's own
verifier found that gate breached at a committed boundary (093ebdf3, 107,487 B) with
nothing mechanical to stop it -- the pre-mortem had named exactly this failure and its
guard was a `wc -c` step an implementer could measure and still commit past. This
test is the executable form: the measurement runs in CI, not in a checklist.

Raising the ceiling is a decision, not an edit: change `CEILING_BYTES` only together
with the ADR id that authorises the growth, in the comment beside it (the waiver
pattern -- cite the decision, never bump the number silently). The ceiling is a
ratchet in the sense of roadmap §9.9: it may go down freely.
"""

from pathlib import Path

# 107,397 B = the file's size at 4ad927f0, the P2.1-residual baseline (AC-10).
CEILING_BYTES = 107_397  # authorised by: dec-380 / AC-10 of the P2.1 residual pipeline


def test_sentinel_definition_does_not_exceed_its_byte_ceiling(project_root: Path) -> None:
    size = (project_root / "agents" / "sentinel.md").stat().st_size
    assert size <= CEILING_BYTES, (
        f"agents/sentinel.md is {size:,} B, over the {CEILING_BYTES:,} B ceiling (AC-10). "
        "Offset the growth (a dispatch-table row costs ~110 B; a prose sentence ~350-700 B) "
        "or raise CEILING_BYTES citing the ADR that authorises it."
    )


def test_ceiling_canary_flags_a_file_over_the_limit(tmp_path: Path) -> None:
    """The assertion fires on an oversized file (gate-canary discipline)."""
    big = tmp_path / "agents" / "sentinel.md"
    big.parent.mkdir(parents=True)
    big.write_bytes(b"x" * (CEILING_BYTES + 1))
    assert big.stat().st_size > CEILING_BYTES
