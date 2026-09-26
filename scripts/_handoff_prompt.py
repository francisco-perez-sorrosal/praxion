"""The prompt a user pastes to start the next window from a handoff.

It points at the handoff rather than restating it: every instruction, decision
and correction the next window needs lives in ``HANDOFF.md``, carried forward
byte-for-byte, so a prompt that paraphrased them would be a second, drifting
copy. What the prompt adds is only what the file cannot say about itself --
where it is, and the order to read it in.
"""

from __future__ import annotations

from pathlib import Path


def continuation_prompt(slug: str, repo_root: Path | str, *, session: bool) -> str:
    """The paste-ready opening message for the next window.

    A pipeline handoff ends in ``/resume-pipeline``, which re-derives the step
    position from ground truth; a session handoff has no pipeline to resume,
    so its next step is the §2 the outgoing window wrote.
    """
    finish = "act on §2 Next action" if session else f"run `/resume-pipeline {slug}`"
    return (
        f"Continue `{slug}` in {repo_root}. Read `.ai-work/{slug}/HANDOFF.md` completely, run its "
        "§0 Preflight and report every line against the value it names before anything else. "
        "Then read §4–§6 (the standing instructions and corrections, carried unchanged) and "
        f"{finish}."
    )
