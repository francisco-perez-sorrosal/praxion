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

import json
from datetime import date
from pathlib import Path

import measure_token_budget as mtb
import pytest


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


def test_count_tokens_is_memoized_per_text_and_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """A repeated request for the same `(text, api_key)` must not pay the
    network round-trip twice -- tests, or a future caller re-deriving an
    already-measured reading, are the realistic cases this guards. It does
    NOT reduce `ratchet()`'s two calls per commit to one: the governed and
    listing corpora are disjoint text (see `count_tokens`'s own docstring).
    """
    mtb.count_tokens.cache_clear()
    calls = {"n": 0}

    class _FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *exc_info: object) -> bool:
            return False

        def read(self) -> bytes:
            return json.dumps({"input_tokens": 42}).encode()

    def _fake_urlopen(request: object, timeout: int) -> _FakeResponse:
        calls["n"] += 1
        return _FakeResponse()

    monkeypatch.setattr(mtb.urllib.request, "urlopen", _fake_urlopen)

    try:
        first = mtb.count_tokens("same text", "key")
        second = mtb.count_tokens("same text", "key")
    finally:
        mtb.count_tokens.cache_clear()

    assert first == 42
    assert second == 42
    assert calls["n"] == 1, "a repeated identical request must not re-hit the network"


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


# -- The ratchet (fixed `today`, stubbed measurements -- no wall clock, no network) --


_TODAY = date(2026, 1, 31)


def _seed_baseline(path: Path, *, listing_ceiling: int, samples: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"schema": 1, "listing_ceiling": listing_ceiling, "samples": samples})
    )


def _stub_measurements(
    monkeypatch: pytest.MonkeyPatch,
    *,
    governed_tokens: int,
    listing_tokens: int,
    governed_measured: bool = True,
    listing_measured: bool = True,
) -> None:
    monkeypatch.setattr(
        mtb,
        "measure",
        lambda repo_root, **kw: {
            "files": ["x"],
            "tokens": governed_tokens,
            "measured": governed_measured,
        },
    )
    monkeypatch.setattr(
        mtb,
        "measure_listing",
        lambda repo_root, **kw: {"tokens": listing_tokens, "measured": listing_measured},
    )


def test_ratchet_positive_governed_delta_blocks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The gate contract: growth over the window must fail, not just report."""
    baseline = tmp_path / "baseline.json"
    _seed_baseline(
        baseline, listing_ceiling=999_999, samples=[{"date": "2026-01-01", "governed_tokens": 100}]
    )
    _stub_measurements(monkeypatch, governed_tokens=150, listing_tokens=10)

    result = mtb.ratchet(tmp_path, baseline_path=baseline, today=_TODAY)

    assert result["governed_delta"] == 50
    assert result["ratchet_ok"] is False


def test_ratchet_relocation_that_nets_non_positive_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A relocation with pointer overhead: net smaller, so it must not block."""
    baseline = tmp_path / "baseline.json"
    _seed_baseline(
        baseline, listing_ceiling=999_999, samples=[{"date": "2026-01-01", "governed_tokens": 200}]
    )
    _stub_measurements(monkeypatch, governed_tokens=195, listing_tokens=10)

    result = mtb.ratchet(tmp_path, baseline_path=baseline, today=_TODAY)

    assert result["governed_delta"] == -5
    assert result["ratchet_ok"] is True


def test_ratchet_listing_over_ceiling_blocks_independent_of_governed_delta(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The listing ceiling is a second, independent tripwire."""
    baseline = tmp_path / "baseline.json"
    _seed_baseline(
        baseline, listing_ceiling=100, samples=[{"date": "2026-01-01", "governed_tokens": 200}]
    )
    _stub_measurements(monkeypatch, governed_tokens=195, listing_tokens=101)

    result = mtb.ratchet(tmp_path, baseline_path=baseline, today=_TODAY)

    assert result["governed_delta"] == -5, "governed side alone would pass"
    assert result["listing_over_ceiling"] is True
    assert result["ratchet_ok"] is False


# -- Basis awareness: a tokenizer count and a fallback estimate are different rulers --


def test_ratchet_skips_the_governed_delta_check_on_a_basis_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A tokenizer-vs-estimate swing (~20% on identical text) must never read
    as growth. The only same-basis prior is 'tokenizer'; today's reading is
    an 'estimate' (no API key) -- the delta check must fail open with a note,
    not manufacture a breach out of two different rulers.
    """
    baseline = tmp_path / "baseline.json"
    _seed_baseline(
        baseline,
        listing_ceiling=999_999,
        samples=[{"date": "2026-01-01", "governed_tokens": 100, "basis": "tokenizer"}],
    )
    _stub_measurements(monkeypatch, governed_tokens=150, listing_tokens=10, governed_measured=False)

    result = mtb.ratchet(tmp_path, baseline_path=baseline, today=_TODAY)

    assert result["governed_delta"] is None
    assert result["ratchet_ok"] is True
    assert any("same-basis" in note for note in result["notes"])


def test_ratchet_skips_the_listing_ceiling_check_on_a_basis_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The frozen ceiling was seeded on 'tokenizer'; today's listing reading
    is an 'estimate' that would breach it if compared directly -- basis
    mismatch must fail this tripwire open too, independent of the governed
    side.
    """
    baseline = tmp_path / "baseline.json"
    baseline.parent.mkdir(parents=True, exist_ok=True)
    baseline.write_text(
        json.dumps(
            {
                "schema": 1,
                "listing_ceiling": 100,
                "listing_ceiling_basis": "tokenizer",
                "samples": [{"date": "2026-01-01", "governed_tokens": 100, "basis": "tokenizer"}],
            }
        )
    )
    _stub_measurements(monkeypatch, governed_tokens=100, listing_tokens=101, listing_measured=False)

    result = mtb.ratchet(tmp_path, baseline_path=baseline, today=_TODAY)

    assert result["listing_over_ceiling"] is False
    assert result["ratchet_ok"] is True
    assert any("listing ceiling" in note for note in result["notes"])


def test_ratchet_same_basis_listing_ceiling_still_blocks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The inverse guard: an explicit, matching basis on both sides must
    still compare -- the mismatch skip must not swallow a real breach.
    """
    baseline = tmp_path / "baseline.json"
    baseline.parent.mkdir(parents=True, exist_ok=True)
    baseline.write_text(
        json.dumps(
            {
                "schema": 1,
                "listing_ceiling": 100,
                "listing_ceiling_basis": "estimate",
                "samples": [{"date": "2026-01-01", "governed_tokens": 100, "basis": "estimate"}],
            }
        )
    )
    _stub_measurements(
        monkeypatch,
        governed_tokens=100,
        listing_tokens=101,
        governed_measured=False,
        listing_measured=False,
    )

    result = mtb.ratchet(tmp_path, baseline_path=baseline, today=_TODAY)

    assert result["listing_over_ceiling"] is True
    assert result["ratchet_ok"] is False
    assert result["notes"] == []


def test_ratchet_within_30_days_skips_the_delta_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bootstrap exemption: under 30 days of history, don't manufacture a verdict."""
    baseline = tmp_path / "baseline.json"
    _seed_baseline(
        baseline, listing_ceiling=999_999, samples=[{"date": "2026-01-15", "governed_tokens": 100}]
    )
    _stub_measurements(monkeypatch, governed_tokens=500, listing_tokens=10)

    result = mtb.ratchet(tmp_path, baseline_path=baseline, today=_TODAY)

    assert result["governed_delta"] is None
    assert result["ratchet_ok"] is True


def test_ratchet_absent_baseline_fails_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every managed project without a seeded baseline must warn and pass, not block."""
    _stub_measurements(monkeypatch, governed_tokens=999_999, listing_tokens=10)

    result = mtb.ratchet(tmp_path, baseline_path=tmp_path / "missing.json", today=_TODAY)

    assert result["skipped"] is True
    assert "baseline" in result["reason"]
    assert result["ratchet_ok"] is True


def test_ratchet_empty_governed_set_fails_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A misconfigured governed glob must not silently pass every future commit as clean."""
    monkeypatch.setattr(mtb, "measure", lambda repo_root, **kw: {"files": [], "tokens": 0})

    result = mtb.ratchet(tmp_path, baseline_path=tmp_path / "unused.json", today=_TODAY)

    assert result["skipped"] is True
    assert "empty" in result["reason"]
    assert result["ratchet_ok"] is True


def test_ratchet_records_todays_sample_idempotently(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A same-day rerun must not duplicate today's entry."""
    baseline = tmp_path / "baseline.json"
    _seed_baseline(
        baseline, listing_ceiling=999_999, samples=[{"date": "2025-12-01", "governed_tokens": 100}]
    )
    _stub_measurements(monkeypatch, governed_tokens=110, listing_tokens=10)

    mtb.ratchet(tmp_path, baseline_path=baseline, today=_TODAY)
    mtb.ratchet(tmp_path, baseline_path=baseline, today=_TODAY)

    samples = json.loads(baseline.read_text())["samples"]
    todays = [s for s in samples if s["date"] == _TODAY.isoformat()]
    assert len(todays) == 1
    assert todays[0]["governed_tokens"] == 110


def test_ratchet_cli_exits_zero_on_a_skip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`--ratchet` at the CLI must not block a commit when there is nothing to ratchet against."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _repo(tmp_path)
    _rule(tmp_path, "small.md", "# a short rule\n")

    assert mtb.main(["--repo-root", str(tmp_path), "--ratchet"]) == 0
