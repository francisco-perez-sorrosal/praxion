"""Tests for resolve_test_scope.py -- the test-topology change-detection resolver.

Gate-liveness contract (`rules/swe/gate-liveness.md`): the resolver decides how
much of a suite runs, so its failure mode is a *false all-clear* -- "no tests to
run" for a change nothing covers. It therefore ships canaries, not just
happy-path tests. Each canary feeds a known-bad input and asserts the resolver
widens; each inverse guard feeds a known-good input and asserts it does not
widen, so the canaries cannot be satisfied by a resolver that escalates always.

The five canary families are `TestEscalation` (load-bearing -- delete the
escalation branch and it reds), `TestClosureRadius` (one fixture chain, three
tiers), `TestParallelSafety`, `TestParserFailsLoudly`, and `TestInverseGuards`.

Import strategy mirrors the sibling script tests: `sys.path` gains the scripts
directory so the module's own `_repo_root` sibling import resolves the same way
it does under `python3 scripts/resolve_test_scope.py`.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent
FIXTURES = SCRIPTS_DIR.parent / "tests" / "fixtures" / "test_topology"
sys.path.insert(0, str(SCRIPTS_DIR))

import resolve_test_scope as rts  # noqa: E402

CHAIN = FIXTURES / "chain_topology.md"
PARALLEL = FIXTURES / "parallel_safety_topology.md"
GLOBS = FIXTURES / "glob_shapes_topology.md"
MALFORMED = FIXTURES / "malformed_anchor_topology.md"
DELETED_SELECTOR_PATH = FIXTURES / "deleted_selector_path_topology.md"


# -- Helpers ------------------------------------------------------------------


def _topology_file(tmp_path: Path, *blocks: str, name: str = "TEST_TOPOLOGY.md") -> Path:
    """Write a topology markdown wrapping each YAML block in a fence."""
    body = "# Topology\n\n" + "\n\n".join(f"```yaml\n{block.strip()}\n```" for block in blocks)
    path = tmp_path / name
    path.write_text(body + "\n", encoding="utf-8")
    return path


def _group_block(
    group_id: str,
    deps: list[str],
    *,
    selectors: str = '  - strategy: pytest-globs\n    arg: ["tests/test_x.py"]',
    boundaries: list[str] | None = None,
    parallel_safe: bool = True,
) -> str:
    lines = [
        f"id: {group_id}",
        f"title: {group_id} group",
        "subsystems:",
        "  - core",
        "tier: unit",
        "selectors:",
        selectors,
        "file_dependencies:",
        *[f'  - "{dep}"' for dep in deps],
    ]
    if boundaries:
        lines.append("integration_boundaries:")
        lines.extend(f"  - {boundary}" for boundary in boundaries)
    lines.append(f"parallel_safe: {'true' if parallel_safe else 'false'}")
    lines.append("shared_fixture_scope: none")
    return "\n".join(lines)


def _resolve(topology: Path, changed: list[str], tier: str = "step", **kwargs) -> dict:
    """Run the pure decision path against an explicit changed set."""
    groups = rts.load_topology(topology)
    changed_set = rts.ChangedSet(tuple(changed), "explicit")
    return rts.resolve(groups, changed_set, tier, topology.parent, topology.name, **kwargs)


def _argvs(payload: dict) -> list[list[str]]:
    return [inv["argv"] for inv in payload["invocations"]]


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _seeded_repo(tmp_path: Path) -> Path:
    """A git repo with one commit -- enough for `HEAD` and a `...HEAD` range to exist."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.invalid")
    _git(repo, "config", "user.name", "T")
    (repo / "seed.txt").write_text("seed\n", encoding="utf-8")
    _git(repo, "add", "seed.txt")
    _git(repo, "commit", "-qm", "seed")
    return repo


def _repo_ignoring_build(tmp_path: Path) -> Path:
    """A repo whose own `.gitignore` excludes `build/`, plus a one-group topology."""
    repo = _seeded_repo(tmp_path)
    (repo / ".gitignore").write_text("build/\n", encoding="utf-8")
    _topology_file(repo, _group_block("alpha", ["src/alpha/**"]))
    return repo


def _resolve_in_repo(repo: Path, changed: list[str]) -> dict:
    """Resolve against a real repo, so `git check-ignore` has something to answer."""
    topology = repo / "TEST_TOPOLOGY.md"
    return rts.resolve(
        rts.load_topology(topology),
        rts.ChangedSet(tuple(changed), "explicit"),
        "step",
        repo,
        topology.name,
    )


# == CANARY 1: escalation (the load-bearing one) ==============================


class TestEscalation:
    """An unmatched changed path must WIDEN the radius, never narrow it."""

    def test_unmapped_source_path_escalates_to_full_suite(self, tmp_path: Path) -> None:
        """The canary. Removing the escalation branch turns this red.

        `src/orphan/new.py` is a source file no group claims. Returning only the
        matched group -- or worse, nothing -- would be a false all-clear for
        every test the orphan file can break.
        """
        topology = _topology_file(
            tmp_path,
            _group_block("alpha", ["src/alpha/**"]),
            _group_block("beta", ["src/beta/**"]),
        )

        payload = _resolve(topology, ["src/alpha/thing.py", "src/orphan/new.py"])

        assert payload["escalated"] is True
        assert payload["escalation_reason"] == rts.REASON_UNMAPPED
        assert payload["selected_group_ids"] == ["alpha", "beta"]

    def test_escalation_names_the_offending_path(self, tmp_path: Path) -> None:
        """ "Escalated" without the culprit is an alarm with no address."""
        topology = _topology_file(tmp_path, _group_block("alpha", ["src/alpha/**"]))

        payload = _resolve(topology, ["src/alpha/thing.py", "src/orphan/new.py"])

        assert payload["escalation_paths"] == ["src/orphan/new.py"]
        assert "src/alpha/thing.py" not in payload["escalation_paths"]

    def test_escalation_overrides_a_narrow_step_tier(self, tmp_path: Path) -> None:
        """`--tier step` must not be able to suppress the safety escalation."""
        topology = _topology_file(
            tmp_path,
            _group_block("alpha", ["src/alpha/**"], boundaries=["beta"]),
            _group_block("beta", ["src/beta/**"]),
        )

        payload = _resolve(topology, ["nope/unmapped.py"], tier="step")

        assert payload["escalated"] is True
        assert payload["selected_group_ids"] == ["alpha", "beta"]

    def test_a_single_unmapped_path_escalates_even_when_others_match(self, tmp_path: Path) -> None:
        """One hole is enough. Majority matching must not dilute the signal."""
        topology = _topology_file(
            tmp_path,
            _group_block("alpha", ["src/alpha/**"]),
            _group_block("beta", ["src/beta/**"]),
        )

        payload = _resolve(
            topology,
            ["src/alpha/a.py", "src/alpha/b.py", "src/beta/c.py", "wild.py"],
        )

        assert payload["escalated"] is True
        assert payload["escalation_paths"] == ["wild.py"]


# == CANARY 2: closure radius =================================================


class TestClosureRadius:
    """One fixture chain (alpha -> beta -> gamma), three tiers, three answers."""

    def test_step_tier_applies_no_closure(self) -> None:
        payload = _resolve(CHAIN, ["src/alpha/x.py"], tier="step")

        assert payload["selected_group_ids"] == ["alpha"]

    def test_phase_tier_is_exactly_one_hop(self) -> None:
        """`beta` is alpha's boundary; `gamma` is beta's and must NOT come along.

        A two-link chain cannot distinguish one-hop from transitive closure --
        gamma is the whole reason the fixture has a third link.
        """
        payload = _resolve(CHAIN, ["src/alpha/x.py"], tier="phase")

        assert payload["selected_group_ids"] == ["alpha", "beta"]
        assert "gamma" not in payload["selected_group_ids"]

    def test_pipeline_tier_runs_everything(self) -> None:
        payload = _resolve(CHAIN, ["src/alpha/x.py"], tier="pipeline")

        assert payload["selected_group_ids"] == ["alpha", "beta", "gamma"]

    def test_pipeline_tier_runs_everything_even_with_no_match(self) -> None:
        """Trunk: pipeline is "full suite regardless of declared boundaries"."""
        payload = _resolve(CHAIN, [], tier="pipeline")

        assert payload["selected_group_ids"] == ["alpha", "beta", "gamma"]
        assert payload["escalated"] is False

    def test_a_dangling_boundary_id_fails_loudly(self, tmp_path: Path) -> None:
        """Silently dropping an unknown boundary would narrow phase closure."""
        topology = _topology_file(
            tmp_path, _group_block("alpha", ["src/alpha/**"], boundaries=["ghost"])
        )

        with pytest.raises(rts.TopologyError, match="ghost"):
            _resolve(topology, ["src/alpha/x.py"], tier="phase")


# == CANARY 3: parallel safety ================================================


class TestParallelSafety:
    """A `parallel_safe: false` group never shares an invocation."""

    def test_unsafe_group_is_never_merged_with_safe_groups(self) -> None:
        payload = _resolve(
            PARALLEL,
            ["src/safe_one/a.py", "src/safe_two/b.py", "src/server/c.py"],
        )

        pooled = [inv for inv in payload["invocations"] if inv["parallelism"] == "parallel-safe"]
        assert len(pooled) == 1
        assert sorted(pooled[0]["groups"]) == ["safe-one", "safe-two"]
        assert "exclusive-port" not in pooled[0]["groups"]
        assert "tests/test_exclusive_port.py" not in pooled[0]["argv"]

    def test_unsafe_group_gets_its_own_sequential_invocation(self) -> None:
        payload = _resolve(PARALLEL, ["src/safe_one/a.py", "src/server/c.py"])

        sequential = [inv for inv in payload["invocations"] if inv["parallelism"] == "sequential"]
        assert [inv["groups"] for inv in sequential] == [["exclusive-port"]]
        assert sequential[0]["argv"] == ["pytest", "tests/test_exclusive_port.py"]

    def test_two_unsafe_groups_do_not_share_an_invocation(self) -> None:
        """Both may hold the same exclusive resource; pooling them re-creates the bug."""
        payload = _resolve(PARALLEL, ["src/server/c.py", "src/db/d.py"])

        sequential = [inv for inv in payload["invocations"] if inv["parallelism"] == "sequential"]
        assert sorted(inv["groups"] for inv in sequential) == [["exclusive-db"], ["exclusive-port"]]

    def test_safe_only_selection_produces_one_pooled_invocation(self) -> None:
        payload = _resolve(PARALLEL, ["src/safe_one/a.py", "src/safe_two/b.py"])

        assert [inv["parallelism"] for inv in payload["invocations"]] == ["parallel-safe"]
        assert _argvs(payload) == [["pytest", "tests/test_safe_one.py", "tests/test_safe_two.py"]]


# == CANARY 4: the parser fails loudly ========================================


class TestParserFailsLoudly:
    """Never skip. A dropped group under-selects and leaves no trace."""

    def test_yaml_alias_raises_naming_file_and_line(self) -> None:
        """A break after a good group must abort the load, not return a partial one.

        The fixture's first group is well-formed on purpose -- that is the case
        in which "skip it and carry on" looks harmless.
        """
        with pytest.raises(rts.TopologyError) as excinfo:
            rts.load_topology(MALFORMED, MALFORMED.name)

        assert excinfo.value.source == MALFORMED.name
        assert excinfo.value.lineno > 1
        assert str(excinfo.value).startswith(f"{MALFORMED.name}:")

    @pytest.mark.parametrize(
        ("block", "needle"),
        [
            pytest.param("id: <kebab-case>\ntitle: t\n", "placeholder", id="schema-placeholder"),
            pytest.param("title: no id here\n", "no string `id`", id="fence-without-id"),
            pytest.param(
                _group_block("a", ["src/**"]) + "\nmystery_key: 1", "unknown key", id="unknown-key"
            ),
            pytest.param("id: a\ntitle: t\n", "missing required key", id="missing-required"),
            pytest.param(_group_block("a", ["/abs/path/**"]), "absolute", id="absolute-dependency"),
            pytest.param(
                _group_block(
                    "a", ["src/**"], selectors='  - strategy: manual\n    arg: ["tests/x.py"]'
                ),
                "cannot materialize",
                id="unregistered-strategy",
            ),
            pytest.param(
                _group_block("a", ["src/**"], selectors="  - strategy: pytest-globs\n    arg: []"),
                "empty flow sequence",
                id="empty-selector-arg",
            ),
            pytest.param(
                "id: a\ntitle: t\nsubsystems: {a: b}\n", "flow mapping", id="flow-mapping"
            ),
            pytest.param("id: a\ntitle: broken\nsubsystems\n", "unrecognized line", id="no-colon"),
        ],
    )
    def test_unrecognized_construct_raises(self, tmp_path: Path, block: str, needle: str) -> None:
        topology = _topology_file(tmp_path, block)

        with pytest.raises(rts.TopologyError, match=needle):
            rts.load_topology(topology)

    @pytest.mark.parametrize(
        "value", ["&anchor", "*alias", "!!str x", "| block", "> folded", "%TAG", "`cmd`", "@rsv"]
    )
    def test_a_yaml_indicator_never_degrades_to_a_plain_string(
        self, tmp_path: Path, value: str
    ) -> None:
        """Pins the indicator guard directly -- the alias fixture does not reach it.

        Mutation-testing found this: with the guard removed, the fixture still
        failed, but on a *later* type check, so the guard was untested. `id: *ref`
        is the shape that matters -- a str-typed field where the fallthrough
        yields a syntactically valid group whose id is the literal `"*ref"`.
        """
        topology = _topology_file(tmp_path, f"id: {value}\ntitle: t\n")

        with pytest.raises(rts.TopologyError, match="unsupported YAML construct"):
            rts.load_topology(topology)

    def test_duplicate_group_id_raises(self, tmp_path: Path) -> None:
        topology = _topology_file(
            tmp_path, _group_block("alpha", ["src/a/**"]), _group_block("alpha", ["src/b/**"])
        )

        with pytest.raises(rts.TopologyError, match="duplicate group id"):
            rts.load_topology(topology)

    def test_empty_topology_raises_rather_than_selecting_nothing(self, tmp_path: Path) -> None:
        """Zero groups would make every change "nothing to run" -- the worst answer."""
        path = tmp_path / "TEST_TOPOLOGY.md"
        path.write_text("# Topology\n\nNo groups yet.\n", encoding="utf-8")

        with pytest.raises(rts.TopologyError, match="no test groups"):
            rts.load_topology(path)

    def test_unterminated_fence_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "TEST_TOPOLOGY.md"
        path.write_text("# T\n\n```yaml\nid: a\n", encoding="utf-8")

        with pytest.raises(rts.TopologyError, match="unterminated"):
            rts.load_topology(path)


# == CANARY 5: inverse guards =================================================


class TestInverseGuards:
    """Known-good inputs that must NOT widen -- otherwise "always escalate" passes."""

    def test_a_matched_change_at_step_tier_does_not_pull_in_boundaries(self) -> None:
        payload = _resolve(CHAIN, ["src/alpha/x.py"], tier="step")

        assert payload["escalated"] is False
        assert payload["selected_group_ids"] == ["alpha"]
        assert _argvs(payload) == [["pytest", "tests/test_alpha.py"]]

    def test_root_narrative_change_does_not_escalate(self, tmp_path: Path) -> None:
        """A README-only commit must not buy a full suite."""
        topology = _topology_file(tmp_path, _group_block("alpha", ["src/alpha/**"]))

        payload = _resolve(topology, ["README.md", "CHANGELOG.md", "LICENSE"])

        assert payload["escalated"] is False
        assert payload["invocations"] == []
        assert {entry["rule"] for entry in payload["ignored_non_source"]} == {
            rts.RULE_ROOT_NARRATIVE
        }

    def test_docs_change_escalates_by_default(self, tmp_path: Path) -> None:
        """Pins the deliberate divergence: `docs/` is NOT a built-in exclusion.

        Excluding it looks obviously right and is wrong at least sometimes: here
        `docs/architecture.md` is reconciled against `.ai-state/DESIGN.md` by a
        gate with tests. Adding `docs/` to the built-in set must mean deleting
        this test on purpose rather than by accident.
        """
        topology = _topology_file(tmp_path, _group_block("alpha", ["src/alpha/**"]))

        payload = _resolve(topology, ["docs/architecture.md"])

        assert payload["escalated"] is True
        assert payload["escalation_paths"] == ["docs/architecture.md"]

    def test_docs_change_is_silent_when_a_group_claims_it(self, tmp_path: Path) -> None:
        """The preferred escape: declare it, and the right group is selected."""
        topology = _topology_file(
            tmp_path,
            _group_block("alpha", ["src/alpha/**"]),
            _group_block("doc-lint", ["docs/**"]),
        )

        payload = _resolve(topology, ["docs/architecture.md"])

        assert payload["escalated"] is False
        assert payload["selected_group_ids"] == ["doc-lint"]

    def test_caller_declared_non_source_glob_suppresses_escalation(self, tmp_path: Path) -> None:
        """The explicit, reported escape hatch -- never a silent default."""
        topology = _topology_file(tmp_path, _group_block("alpha", ["src/alpha/**"]))

        payload = _resolve(topology, ["docs/guide.md"], non_source_globs=("docs/**",))

        assert payload["escalated"] is False
        assert payload["ignored_non_source"] == [
            {"path": "docs/guide.md", "rule": rts.RULE_CALLER_DECLARED}
        ]

    def test_nested_readme_still_escalates(self, tmp_path: Path) -> None:
        """`root-narrative` is root-scoped: a nested README may be a fixture."""
        topology = _topology_file(tmp_path, _group_block("alpha", ["src/alpha/**"]))

        payload = _resolve(topology, ["tests/fixtures/README.md"])

        assert payload["escalated"] is True

    def test_root_level_non_prose_file_still_escalates(self, tmp_path: Path) -> None:
        """`pyproject.toml` and `Makefile` are root-level and unambiguously source."""
        topology = _topology_file(tmp_path, _group_block("alpha", ["src/alpha/**"]))

        payload = _resolve(topology, ["pyproject.toml", "Makefile", "CLAUDE.md"])

        assert payload["escalated"] is True
        assert sorted(payload["escalation_paths"]) == ["CLAUDE.md", "Makefile", "pyproject.toml"]

    def test_no_changes_runs_nothing_at_step_tier(self, tmp_path: Path) -> None:
        topology = _topology_file(tmp_path, _group_block("alpha", ["src/alpha/**"]))

        payload = _resolve(topology, [])

        assert payload["escalated"] is False
        assert payload["invocations"] == []


# == Glob semantics ===========================================================


class TestGlobSemantics:
    """`**` needs care: `fnmatch` has no notion of it and its `*` crosses `/`."""

    @pytest.mark.parametrize(
        ("pattern", "path", "expected"),
        [
            ("src/single/*.py", "src/single/a.py", True),
            ("src/single/*.py", "src/single/nested/deep.py", False),
            ("src/single/*.py", "src/single/a.txt", False),
            ("src/tree/**", "src/tree/a.py", True),
            ("src/tree/**", "src/tree/x/y/z.py", True),
            ("src/tree/**", "src/tree", False),
            ("src/tree/**", "src/other/a.py", False),
            ("src/mid/**/conf.py", "src/mid/conf.py", True),
            ("src/mid/**/conf.py", "src/mid/a/conf.py", True),
            ("src/mid/**/conf.py", "src/mid/a/b/conf.py", True),
            ("src/mid/**/conf.py", "src/mid/a/other.py", False),
            ("**/legacy.py", "legacy.py", True),
            ("**/legacy.py", "a/b/legacy.py", True),
            ("**/legacy.py", "a/legacy.pyc", False),
            ("src/exact/one.py", "src/exact/one.py", True),
            ("src/exact/one.py", "src/exact/two.py", False),
            ("src/bare", "src/bare/inside.py", False),
            ("src/?.py", "src/a.py", True),
            ("src/?.py", "src/ab.py", False),
            ("src/[ab].py", "src/a.py", True),
            ("src/[ab].py", "src/c.py", False),
            ("src/[!ab].py", "src/c.py", True),
            ("src/[!ab].py", "src/a.py", False),
        ],
    )
    def test_glob_matching(self, pattern: str, path: str, expected: bool) -> None:
        assert bool(rts.glob_to_regex(pattern).match(path)) is expected

    def test_single_star_does_not_cross_a_separator_end_to_end(self) -> None:
        """The fnmatch trap, end to end -- over-matching is the dangerous direction.

        Nobody claims `src/single/nested/deep.py`, so an over-matching `*` would
        silently *narrow* the run by suppressing the escalation.
        """
        payload = _resolve(GLOBS, ["src/single/nested/deep.py"])

        assert payload["escalated"] is True
        assert payload["matched_group_ids"] == []

    def test_trailing_doublestar_reaches_every_depth(self) -> None:
        payload = _resolve(GLOBS, ["src/tree/a/b/c/deep.py"])

        assert payload["escalated"] is False
        assert payload["selected_group_ids"] == ["trailing-doublestar"]

    def test_interior_doublestar_matches_zero_segments(self) -> None:
        payload = _resolve(GLOBS, ["src/mid/conf.py"])

        assert payload["selected_group_ids"] == ["interior-doublestar"]

    def test_bare_directory_pattern_does_not_expand_to_its_subtree(self) -> None:
        """Under-matching escalates, which is safe; expanding it would not be."""
        payload = _resolve(GLOBS, ["src/bare/inside.py"])

        assert payload["escalated"] is True

    def test_one_path_may_select_several_groups(self) -> None:
        payload = _resolve(GLOBS, ["src/tree/legacy.py"])

        assert sorted(payload["selected_group_ids"]) == [
            "leading-doublestar",
            "trailing-doublestar",
        ]


# == Invocation composition ===================================================


class TestInvocationComposition:
    """Union per strategy -- never across strategies, which pytest would AND."""

    def test_globs_are_unioned_across_groups(self, tmp_path: Path) -> None:
        topology = _topology_file(
            tmp_path,
            _group_block(
                "a", ["src/a/**"], selectors='  - strategy: pytest-globs\n    arg: ["tests/a.py"]'
            ),
            _group_block(
                "b", ["src/b/**"], selectors='  - strategy: pytest-globs\n    arg: ["tests/b.py"]'
            ),
        )

        payload = _resolve(topology, ["src/a/x.py", "src/b/y.py"])

        assert _argvs(payload) == [["pytest", "tests/a.py", "tests/b.py"]]

    def test_markers_are_or_joined(self, tmp_path: Path) -> None:
        topology = _topology_file(
            tmp_path,
            _group_block(
                "a", ["src/a/**"], selectors='  - strategy: pytest-markers\n    arg: ["mark_a"]'
            ),
            _group_block(
                "b", ["src/b/**"], selectors='  - strategy: pytest-markers\n    arg: ["mark_b"]'
            ),
        )

        payload = _resolve(topology, ["src/a/x.py", "src/b/y.py"])

        assert _argvs(payload) == [["pytest", "-m", "mark_a or mark_b"]]

    def test_keyword_expressions_are_parenthesised_before_joining(self, tmp_path: Path) -> None:
        """`a or b` + `c` unioned bare would bind as `a or (b and c)`."""
        topology = _topology_file(
            tmp_path,
            _group_block(
                "a",
                ["src/a/**"],
                selectors='  - strategy: pytest-keywords\n    arg: "alpha or beta"',
            ),
            _group_block(
                "b", ["src/b/**"], selectors='  - strategy: pytest-keywords\n    arg: "gamma"'
            ),
        )

        payload = _resolve(topology, ["src/a/x.py", "src/b/y.py"])

        assert _argvs(payload) == [["pytest", "-k", "(alpha or beta) or (gamma)"]]

    def test_strategies_never_collapse_into_one_pytest_call(self, tmp_path: Path) -> None:
        """`pytest paths -m marks` INTERSECTS them -- that would silently under-run."""
        topology = _topology_file(
            tmp_path,
            _group_block(
                "a",
                ["src/a/**"],
                selectors=(
                    '  - strategy: pytest-globs\n    arg: ["tests/a.py"]\n'
                    '  - strategy: pytest-markers\n    arg: ["mark_a"]'
                ),
            ),
        )

        payload = _resolve(topology, ["src/a/x.py"])

        assert _argvs(payload) == [["pytest", "tests/a.py"], ["pytest", "-m", "mark_a"]]

    def test_duplicate_selector_args_are_deduplicated(self, tmp_path: Path) -> None:
        topology = _topology_file(
            tmp_path,
            _group_block(
                "a", ["src/a/**"], selectors='  - strategy: pytest-globs\n    arg: ["tests/x.py"]'
            ),
            _group_block(
                "b", ["src/b/**"], selectors='  - strategy: pytest-globs\n    arg: ["tests/x.py"]'
            ),
        )

        payload = _resolve(topology, ["src/a/1.py", "src/b/2.py"])

        assert _argvs(payload) == [["pytest", "tests/x.py"]]


# == Changed-set derivation ===================================================


class TestChangedSet:
    def test_explicit_paths_are_reported_as_explicit(self, tmp_path: Path) -> None:
        result = rts.changed_paths(["b.py", "a.py"], None, tmp_path)

        assert result.source == "explicit"
        assert result.paths == ("a.py", "b.py")

    def test_absolute_path_inside_the_repo_is_relativised(self, tmp_path: Path) -> None:
        target = tmp_path / "src" / "a.py"
        target.parent.mkdir(parents=True)
        target.write_text("x\n", encoding="utf-8")

        result = rts.changed_paths([str(target)], None, tmp_path)

        assert result.paths == ("src/a.py",)

    def test_absolute_path_outside_the_repo_fails_loudly(self, tmp_path: Path) -> None:
        outside = tmp_path.parent / "elsewhere.py"

        with pytest.raises(rts.TopologyError, match="outside the repo root"):
            rts.changed_paths([str(outside)], None, tmp_path / "repo")

    def test_working_tree_default_includes_untracked_files(self, tmp_path: Path) -> None:
        """A brand-new source file is absent from `git diff HEAD`.

        Omitting it would under-select exactly when the blast radius is least
        known -- so untracked-but-not-ignored files count as changed.
        """
        repo = _seeded_repo(tmp_path)
        (repo / "seed.txt").write_text("edited\n", encoding="utf-8")
        (repo / "brand_new.py").write_text("x = 1\n", encoding="utf-8")

        result = rts.changed_paths(None, None, repo)

        assert result.source == "working-tree"
        assert set(result.paths) == {"seed.txt", "brand_new.py"}

    def test_changed_from_uses_the_three_dot_range(self, tmp_path: Path) -> None:
        repo = _seeded_repo(tmp_path)
        base = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
        ).stdout.strip()
        (repo / "later.py").write_text("x = 1\n", encoding="utf-8")
        _git(repo, "add", "later.py")
        _git(repo, "commit", "-qm", "later")

        result = rts.changed_paths(None, base, repo)

        assert result.paths == ("later.py",)
        assert result.source == f"git-diff:{base}...HEAD"

    def test_a_bad_git_ref_fails_loudly(self, tmp_path: Path) -> None:
        with pytest.raises(rts.TopologyError, match="git diff"):
            rts.changed_paths(None, "no-such-ref", _seeded_repo(tmp_path))


class TestGitIgnoredExclusion:
    """`git-ignored` is derived from the project's own declaration, not this tool's taste."""

    def test_gitignored_path_does_not_escalate(self, tmp_path: Path) -> None:
        payload = _resolve_in_repo(_repo_ignoring_build(tmp_path), ["build/out.js"])

        assert payload["escalated"] is False
        assert payload["ignored_non_source"] == [
            {"path": "build/out.js", "rule": rts.RULE_GIT_IGNORED}
        ]

    def test_a_tracked_sibling_of_an_ignored_path_still_escalates(self, tmp_path: Path) -> None:
        payload = _resolve_in_repo(
            _repo_ignoring_build(tmp_path), ["build/out.js", "src/other/real.py"]
        )

        assert payload["escalated"] is True
        assert payload["escalation_paths"] == ["src/other/real.py"]

    def test_dot_git_internals_are_never_source(self, tmp_path: Path) -> None:
        topology = _topology_file(tmp_path, _group_block("alpha", ["src/alpha/**"]))

        payload = _resolve(topology, [".git/HEAD"])

        assert payload["escalated"] is False


# == CLI surface ==============================================================


class TestCli:
    @staticmethod
    def _run(tmp_path: Path, changed: str, *extra: str) -> int:
        topology = _topology_file(tmp_path, _group_block("alpha", ["src/alpha/**"]))
        return rts.main(
            [
                "--changed",
                changed,
                "--topology",
                str(topology),
                "--repo-root",
                str(tmp_path),
                *extra,
            ]
        )

    def test_json_payload_round_trips(self, tmp_path: Path, capsys) -> None:
        code = self._run(tmp_path, "src/alpha/x.py", "--tier", "step", "--json")

        payload = json.loads(capsys.readouterr().out)
        assert code == rts.EXIT_OK
        assert payload["selected_group_ids"] == ["alpha"]
        assert payload["invocations"][0]["argv"] == ["pytest", "tests/test_x.py"]

    def test_human_mode_puts_commands_on_stdout_and_context_on_stderr(
        self, tmp_path: Path, capsys
    ) -> None:
        """`resolve_test_scope.py | sh` must not be poisoned by commentary."""
        self._run(tmp_path, "src/alpha/x.py")

        captured = capsys.readouterr()
        assert captured.out.strip() == "pytest tests/test_x.py"
        assert "selected groups: alpha" in captured.err

    def test_escalation_is_announced_on_stderr(self, tmp_path: Path, capsys) -> None:
        self._run(tmp_path, "src/orphan/x.py")

        err = capsys.readouterr().err
        assert "ESCALATED to full suite" in err
        assert "src/orphan/x.py" in err

    def test_topology_error_exits_two(self, tmp_path: Path, capsys) -> None:
        code = rts.main(["--changed", "a.py", "--topology", str(tmp_path / "absent.md")])

        assert code == rts.EXIT_ERROR
        assert "error:" in capsys.readouterr().err

    def test_mutually_exclusive_change_sources_exit_two(self, tmp_path: Path) -> None:
        code = rts.main(["--changed", "a.py", "--changed-from", "HEAD~1"])

        assert code == rts.EXIT_ERROR

    def test_help_runs_under_the_ambient_interpreter(self) -> None:
        """The script is invoked as a bare `python3 scripts/...` by agent prose."""
        result = subprocess.run(
            ["python3", str(SCRIPTS_DIR / "resolve_test_scope.py"), "--help"],
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0, result.stderr
        assert "--changed-from" in result.stdout


class TestStdlibOnly:
    """Canary for the ambient-interpreter constraint.

    A bare `python3` here is a 3.14 alpha with neither pytest nor pyyaml. A
    third-party import would make this script a finding of the repository's own
    ambient-import check -- and, worse, it would die on import at exactly the
    call sites that cannot report why.
    """

    @pytest.mark.parametrize("module", ["resolve_test_scope.py", "_topology_yaml.py"])
    def test_imports_nothing_third_party(self, module: str) -> None:
        """The sibling is covered too: the constraint is transitive through imports."""
        tree = ast.parse((SCRIPTS_DIR / module).read_text(encoding="utf-8"))
        siblings = {path.stem for path in SCRIPTS_DIR.glob("*.py")}
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported |= {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                imported.add(node.module.split(".")[0])

        assert not (imported - set(sys.stdlib_module_names) - siblings)

    def test_the_parser_sibling_is_not_executable(self) -> None:
        """A library, not a tool -- the installer's `-f && -x` filter must skip it."""
        assert not (SCRIPTS_DIR / "_topology_yaml.py").stat().st_mode & 0o111


# == Selector resolution (td-143) =============================================
#
# `resolve_test_scope.py` never checks that a `pytest-globs` selector `arg`
# resolves to anything on disk -- it only ever *reads* `selectors` to compose
# an invocation, never validates them. That is exactly how the incident this
# guards against reached green: splitting `tests/test_ci_autofix_hub_invariants.py`
# left the `ci-workflows` group's selector naming a deleted path, the resulting
# `pytest <deleted-path>` invocation exited 4, and nothing in the suite noticed
# because a test group that silently stops selecting anything is
# indistinguishable from one that passes.
#
# Scope is deliberately `pytest-globs` only: `pytest-markers` args are marker
# names and `pytest-keywords` args are `-k` expressions, neither of which is a
# filesystem path, so validating them here would be a category error.
#
# Glob decision: a glob selector arg (one containing `*`, `?`, or `[`) is held
# to the same standard as a literal one -- it must match at least one path.
# A glob matching zero files is the identical false-green in a different
# shape: the group's invocation still exits cleanly (pytest's own "no tests
# collected" is exit code 5, not a hard failure a caller would notice), so
# nothing distinguishes "covers nothing today" from "covers nothing anymore".
# Held to a lower bar than the literal case would silently reintroduce the
# same gap this check exists to close. `pathlib.Path.glob` (not
# `resolve_test_scope.glob_to_regex`) is used to evaluate the match -- it is a
# deliberately simpler proxy answering only "does anything match", not the
# production module's exact segment-boundary semantics, which is all this
# existence check needs.


def _unresolved_pytest_globs_args(groups: tuple, repo_root: Path) -> list[str]:
    """`pytest-globs` selector args that don't resolve against `repo_root`.

    A literal arg (no glob metacharacter) must exist as a file or directory.
    A glob arg must match at least one path. Returns one message per problem,
    prefixed with the owning group id, so a failure names both the group and
    the arg without further digging.
    """
    problems: list[str] = []
    for group in groups:
        for selector in group.selectors:
            if selector.strategy != "pytest-globs":
                continue
            for arg in selector.args:
                if any(ch in arg for ch in "*?["):
                    if not any(repo_root.glob(arg)):
                        problems.append(
                            f"{group.id}: glob {arg!r} matches no path under {repo_root}"
                        )
                elif not (repo_root / arg).exists():
                    problems.append(
                        f"{group.id}: {arg!r} does not resolve to a path under {repo_root}"
                    )
    return problems


class TestSelectorPathResolution:
    def test_real_topology_selector_args_all_resolve(self) -> None:
        """Regression guard: every selector in the live topology names a real path.

        This is the check itself, run against `.ai-state/TEST_TOPOLOGY.md`. A
        future module split that forgets to update a selector fails loudly
        here instead of shipping a group that silently selects nothing.
        """
        repo_root = SCRIPTS_DIR.parent
        groups = rts.load_topology(repo_root / rts.DEFAULT_TOPOLOGY)

        problems = _unresolved_pytest_globs_args(groups, repo_root)

        assert problems == [], "\n".join(problems)

    def test_canary_flags_selector_arg_naming_a_deleted_path(self) -> None:
        """The gate bites: a deleted path is flagged, a real one is not.

        Four groups in one fixture -- literal-real, literal-deleted,
        glob-empty, glob-nonempty -- so the assertion proves discrimination,
        not just "fires on something".
        """
        groups = rts.load_topology(DELETED_SELECTOR_PATH)

        problems = _unresolved_pytest_globs_args(groups, FIXTURES)

        flagged = {p.split(":", 1)[0] for p in problems}
        assert flagged == {"has-deleted-path", "has-empty-glob"}
