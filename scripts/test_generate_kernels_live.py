"""Tests for generate_kernels.py over the real repository.

Each role's module set, the committed kernels being fresh, the shared stop-line wording, the
cap, the live definitions changing only by the lines of their blocks, the live preamble and
the live spawn split: the checks that read what the rules say today, paired with the
synthetic canaries in the sibling test modules that prove the same checks bite.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))

import _rule_delivery as rd  # noqa: E402  # pyright: ignore[reportMissingImports]
import check_agent_shared_blocks as sb  # noqa: E402
import generate_kernels as gk  # noqa: E402
import kernel_model as km  # noqa: E402
import kernel_spawn_split as kss  # noqa: E402
from _generate_kernels_testkit import (  # noqa: E402
    CAP,
    REPO_ROOT,
    TODAYS_PREAMBLE,
)

# -- The real repository ---------------------------------------------------------------------


@pytest.fixture(scope="module")
def live() -> gk.KernelPlan:
    return gk.plan_kernels(REPO_ROOT)


WRITER_ROLES = ("systems-architect", "implementation-planner", "interface-designer")
LIVE_MODULES = {
    "verifier": ("adr-reader", "ledger-writer", "principles-anchor", "local-verifier"),
    "sentinel": ("ledger-writer",),
    "architect-validator": ("ledger-writer",),
    "systems-architect": ("adr-author", "principles-digest", "principles-prior-art"),
    "implementation-planner": ("adr-author",),
    "interface-designer": ("adr-author",),
    "agentic-transactions-architect": ("adr-author",),
    "promethean": ("principles-digest", "principles-prior-art"),
    "roadmap-cartographer": ("delegator",),
    "researcher": ("adr-reader", "principles-prior-art"),
    "context-engineer": ("local-context-engineer",),
    "discipline-consultant": (),
    "skill-genesis": (),
    "implementer": (),
}


@pytest.mark.parametrize("role", LIVE_MODULES)
def test_each_role_holds_the_core_and_its_own_modules(live: gk.KernelPlan, role: str) -> None:
    assert live.assembled_kernel(role).modules == ("core", *LIVE_MODULES[role])


def test_the_verifier_holds_no_adr_author_text(live: gk.KernelPlan) -> None:
    adr_author = live.files[f"{gk.KERNELS_DIR}/adr-author.md"].decode()
    held = "\n".join(s.text for s in live.assembled_kernel("verifier").strings)

    paragraphs = [p for p in adr_author.split("\n\n") if len(p) > 80]
    assert paragraphs
    assert [p for p in paragraphs if p in held] == []


def test_only_the_context_engineer_holds_the_audit_subject_exemption(live: gk.KernelPlan) -> None:
    exemption = "as an audit subject"
    holders = [
        role
        for role, kernel in live.roles.items()
        if exemption in "\n".join(s.text for s in kernel.strings)
    ]

    assert holders == ["context-engineer"]


@pytest.mark.parametrize("role", ["context-engineer", "skill-genesis", "discipline-consultant"])
def test_a_kernel_words_the_stop_line_as_its_definition_does(
    live: gk.KernelPlan, role: str
) -> None:
    held = "\n".join(s.text for s in live.assembled_kernel(role).strings)
    definition = (REPO_ROOT / "agents" / f"{role}.md").read_text(encoding="utf-8")

    for text in (held, definition):
        assert "Stopped at" in text
        assert "Failed at" not in text


def test_every_live_string_and_file_fits_one_injected_string(live: gk.KernelPlan) -> None:
    strings = [len(s.text) for kernel in live.roles.values() for s in kernel.strings]
    files = [
        len(data.decode())
        for rel, data in live.files.items()
        if rel.startswith(gk.KERNELS_DIR) and rel.endswith(".md")
    ]

    assert max(strings) <= CAP
    assert max(files) <= CAP


# The definitions' blocks and the preamble are derived as well; the manifest checker holds them
# fresh once the first generated commit has made them so.
def test_the_committed_kernels_are_what_the_generator_produces(live: gk.KernelPlan) -> None:
    kernel_files = {rel: data for rel, data in live.files.items() if rel.startswith(gk.KERNELS_DIR)}

    assert gk.stale_files(REPO_ROOT, kernel_files) == []


@pytest.mark.parametrize("name", sorted(km.agent_definitions(REPO_ROOT)))
def test_a_live_definition_changes_only_by_the_lines_of_its_blocks(
    live: gk.KernelPlan, name: str
) -> None:
    universal = [b for b in sb.SHARED_BLOCKS if b.universal]
    blocks_file = live.files[f"{gk.KERNELS_DIR}/{gk.BLOCKS_FILE}"].decode()
    block_lines = {line for line in blocks_file.splitlines() if line.strip()}
    path = gk.definition_path(name)
    before = (REPO_ROOT / path).read_text().splitlines()
    after = live.files[path].decode().splitlines()

    def carries(line: str) -> bool:
        return any(line.startswith(b.anchor) or any(t in line for t in b.tells) for b in universal)

    carried = [line for line in before if carries(line)]  # a per-agent sentence may move out of one

    assert [line for line in before if line not in after and not carries(line)] == []
    assert [
        line
        for line in after
        if line not in before
        and line not in block_lines
        and not any(line in old for old in carried)
    ] == []


def test_the_live_preamble_is_todays_wording_within_todays_bound(live: gk.KernelPlan) -> None:
    namespace: dict[str, str] = {}

    exec(live.files[gk.PREAMBLE_PATH].decode(), namespace)

    assert namespace["_PREAMBLE"] == TODAYS_PREAMBLE


def test_the_live_split_is_what_the_hook_trusts_for_every_unit_it_lists() -> None:
    split = rd.parse_spawn_split((REPO_ROOT / kss.SPAWN_SPLIT_PATH).read_text(encoding="utf-8"))
    assert split is not None
    manifest_sha = kss.sha256_hex((REPO_ROOT / km.MANIFEST_PATH).read_bytes())
    units = {
        unit.unit_id: rd.rule_body((REPO_ROOT / unit.path).read_text(encoding="utf-8"))
        for unit in rd.MANAGED_CORE_UNITS
    }

    delivered = rd.spawn_units(units, split, manifest_sha)

    assert {unit_id for unit_id in split.units if delivered[unit_id] != units[unit_id]} == set(
        split.units
    )
    assert all(delivered[unit_id] == entry.text for unit_id, entry in split.units.items())
