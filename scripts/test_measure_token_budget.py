"""Tests for measure_token_budget.py — the always-loaded budget reading.

Cites: rules/swe/gate-liveness.md — a CODE gate ships a canary proving it bites
on a known-bad input. Here that means an over-budget corpus must exit non-zero,
not merely that a healthy corpus reports a number.

Every test drives the offline path (`api_key=None`). The tokenizer path needs
a network call and a key, so exercising it here would make the suite
non-deterministic and environment-dependent — the two properties this file's
own subject matter exists to eliminate.
"""

from __future__ import annotations

from pathlib import Path

import measure_token_budget as mtb


def _rule(root: Path, rel: str, body: str) -> Path:
    path = root / "rules" / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _repo(root: Path) -> Path:
    (root / "CLAUDE.md").write_text("# project\n", encoding="utf-8")
    return root


# -- The file set (the half that used to be prose) -----------------------------


def test_a_path_scoped_rule_is_not_always_loaded(tmp_path: Path) -> None:
    """`paths:` frontmatter means the rule loads conditionally, so it is out."""
    _repo(tmp_path)
    _rule(tmp_path, "scoped.md", "---\npaths: ['**/*.py']\n---\n\nbody\n")
    _rule(tmp_path, "unscoped.md", "# always on\n")

    names = {Path(f).name for f in mtb.always_loaded_files(tmp_path, include_global=False)}

    assert names == {"unscoped.md", "CLAUDE.md"}


def test_a_catalog_readme_is_not_always_loaded(tmp_path: Path) -> None:
    """The exclusion worth ~4,500 tokens, and the one that flipped past verdicts.

    A catalog README carries no `paths:` and so reads as always-loaded under a
    naive "no frontmatter means always loaded" test, but a live session does not
    inject it. Counting it in is the single largest source of basis drift.
    """
    _repo(tmp_path)
    _rule(tmp_path, "README.md", "# catalog\n" + "x" * 5000)
    _rule(tmp_path, "real.md", "# a rule\n")

    names = {Path(f).name for f in mtb.always_loaded_files(tmp_path, include_global=False)}

    assert "README.md" not in names
    assert "real.md" in names


# -- The reading ---------------------------------------------------------------


def test_canary_an_over_budget_corpus_exits_nonzero(tmp_path: Path) -> None:
    """The gate contract: a corpus past the ceiling must fail, not just report."""
    _repo(tmp_path)
    _rule(tmp_path, "huge.md", "word " * 40_000)  # far past 25,000 tokens

    report = mtb.measure(tmp_path, api_key=None)

    assert report["over_by"] > 0, "an oversized corpus must register as over budget"
    assert mtb.main(["--repo-root", str(tmp_path)]) == 1


def test_a_corpus_within_budget_exits_zero(tmp_path: Path) -> None:
    """The inverse guard — a healthy corpus must not fail."""
    _repo(tmp_path)
    _rule(tmp_path, "small.md", "# a short rule\n")

    assert mtb.main(["--repo-root", str(tmp_path)]) == 0


def test_a_missing_api_key_degrades_to_a_labelled_estimate(tmp_path: Path) -> None:
    """No key is not a failure, but the reading must not claim to be measured.

    Reporting an estimate as a measurement is how a folk divisor became load
    bearing in the first place; the label is the whole guard against a repeat.
    """
    _repo(tmp_path)
    _rule(tmp_path, "small.md", "# a short rule\n")

    report = mtb.measure(tmp_path, api_key=None)

    assert report["measured"] is False
    assert "estimate" in report["basis"]
    assert report["chars_per_token"] is None, "an estimate cannot report a true ratio"


def test_the_fallback_divisor_errs_high_against_the_measured_ratio(tmp_path: Path) -> None:
    """A guardrail must overestimate, so the fallback has to sit below the truth.

    Pins the direction of the error rather than the number: if a future
    measurement moves the true ratio below the fallback, the estimate would
    start under-reporting and quietly hide a breach.
    """
    assert mtb._FALLBACK_DIVISOR < mtb._MEASURED_RATIO


# -- The listing surface (skill/command/agent `description:` frontmatter) ------


def _skill(root: Path, name: str, description: str, body: str) -> None:
    path = root / "skills" / name / "SKILL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\nname: {name}\ndescription: {description}\n---\n\n{body}\n")


def _command(root: Path, name: str, description: str, body: str) -> None:
    path = root / "commands" / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'---\ndescription: "{description}"\n---\n\n{body}\n')


def _agent(root: Path, name: str, description_lines: list[str], body: str) -> None:
    path = root / "agents" / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    folded = "\n".join(f"  {line}" for line in description_lines)
    path.write_text(f"---\nname: {name}\ndescription: >\n{folded}\n---\n\n{body}\n")


def test_listing_counts_only_frontmatter_descriptions_not_body_text(tmp_path: Path) -> None:
    """The counter's whole job: description in, body out."""
    _skill(tmp_path, "a-skill", "short skill description", "z" * 5000)
    _command(tmp_path, "a-command", "short command description", "z" * 5000)
    _agent(
        tmp_path,
        "an-agent",
        ["a folded", "agent description"],
        "z" * 5000,
    )

    with_body = mtb.measure_listing(tmp_path, api_key=None)
    without_bodies = "\n".join(
        [
            "short skill description",
            "short command description",
            "a folded agent description",
        ]
    )
    expected_bytes = len(without_bodies.encode("utf-8"))

    assert with_body["bytes"] == expected_bytes
    assert with_body["file_count"] == 3


def test_listing_folded_block_scalar_description_is_joined_on_one_line(tmp_path: Path) -> None:
    """The `>` folded-scalar shape used across most skills/agents."""
    _agent(tmp_path, "folded-agent", ["line one of the", "folded description"], "body\n")

    (tmp_path / "skills").mkdir(exist_ok=True)
    (tmp_path / "commands").mkdir(exist_ok=True)

    descriptions_only = mtb.listing_files(tmp_path)
    text = (tmp_path / "agents" / "folded-agent.md").read_text(encoding="utf-8")
    frontmatter = mtb._frontmatter_block(text)

    assert descriptions_only == [tmp_path / "agents" / "folded-agent.md"]
    assert mtb._extract_description(frontmatter) == "line one of the folded description"


def test_listing_single_line_quoted_description_is_unquoted(tmp_path: Path) -> None:
    """The single-line `"..."` shape used across most commands."""
    _command(tmp_path, "quoted-command", "a quoted description", "body\n")

    text = (tmp_path / "commands" / "quoted-command.md").read_text(encoding="utf-8")
    frontmatter = mtb._frontmatter_block(text)

    assert mtb._extract_description(frontmatter) == "a quoted description"


def test_listing_reports_a_labelled_estimate_without_an_api_key(tmp_path: Path) -> None:
    """Same estimate-labelling discipline as the governed reading."""
    _command(tmp_path, "solo-command", "a description", "body\n")

    listing = mtb.measure_listing(tmp_path, api_key=None)

    assert "estimate" in listing["basis"]
    assert listing["tokens"] == round(listing["bytes"] / mtb._FALLBACK_DIVISOR)
