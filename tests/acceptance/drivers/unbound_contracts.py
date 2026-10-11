"""Unbound drivers: contracts the scenarios need that no step has bound to a real interface yet.

Each function raises, in the words of the assumption it stands for, until a driver-binding step
replaces its body. Nothing here imports the system under test.
"""

from __future__ import annotations

from pathlib import Path


def sentinel_frontmatter_key_check_accepts(key: str, sandbox: Path) -> bool:
    """Whether the sentinel's skill-frontmatter key check leaves `key` unflagged.

    Assumed contract: the artifact-conformance family runs on a scratch repository holding one
    skill whose frontmatter uses `key`, and reports a frontmatter-key finding naming that skill
    and key exactly when the key is outside the set it recognises.
    """
    raise NotImplementedError(
        "unbound: the sentinel's skill-frontmatter key check has no bound driver yet; the "
        "scenario waits on the open question about which sites define the accepted field set"
    )


def plugin_eval_cases(skill: str) -> list[Path]:
    """The `claude plugin eval` case directories that probe whether `skill` triggers.

    Assumed contract: each case is a directory holding a `prompt.md` and graders, outside every
    shipped skill directory, in an eval directory the runner finds from the checkout; a trigger
    check is a `tool_used` grader on the `Skill` tool naming the skill, and a must-not-invoke check
    carries a zero ceiling scored in both arms.
    """
    raise NotImplementedError(
        "unbound: no location or grader file format is fixed yet for the plugin eval cases that "
        "probe a skill's triggering"
    )
