"""Tests for count_spawn_shed.py -- the no-cost count of the text a split recipient sheds.

Each test builds a small plugin root in a temporary directory (two core rules, the audience
manifest's bytes and a spawn split cut from them) and runs the command in process. Token
counting is the offline estimate unless a test swaps the tokenizer's counter for a fake.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))

import _rule_delivery as rd  # noqa: E402  # pyright: ignore[reportMissingImports]
import count_spawn_shed as css  # noqa: E402
import kernel_spawn_split as kss  # noqa: E402
import measure_token_budget as mtb  # noqa: E402

PROTOCOL, INTERMEDIATE = rd.MANAGED_CORE_UNITS[0], rd.MANAGED_CORE_UNITS[1]
MANIFEST = "version: 1\n"
KEPT = "# Title\n\nKept text.\n\n"
DROPPED = "## Orchestrator only\n\nDropped text that is longer than the kept text.\n"
FRONTMATTER = "---\ncore: true\n---\n"


def label(unit: rd.CoreUnit) -> str:
    return f"{rd.LABEL_PREFIX}: {unit.unit_id}, part 1 of 1\n\n"


def build_plugin(root: Path, *, split_units: tuple[rd.CoreUnit, ...] = (PROTOCOL, INTERMEDIATE)):
    """Write the two rules whole, the manifest and a spawn split dropping DROPPED from each."""
    for unit in (PROTOCOL, INTERMEDIATE):
        (root / unit.path).parent.mkdir(parents=True, exist_ok=True)
        (root / unit.path).write_text(FRONTMATTER + KEPT + DROPPED, encoding="utf-8")
    (root / rd.AUDIENCE_MANIFEST_PATH).parent.mkdir(parents=True, exist_ok=True)
    (root / rd.AUDIENCE_MANIFEST_PATH).write_text(MANIFEST, encoding="utf-8")
    write_split(root, split_units)


def write_split(root: Path, units: tuple[rd.CoreUnit, ...], manifest_sha: str | None = None):
    whole = KEPT + DROPPED
    entry = rd.SplitEntry("rules/swe/x.md", kss.sha256_hex(whole), KEPT, kss.sha256_hex(KEPT))
    artifact = kss.render_spawn_split(
        manifest_sha or kss.sha256_hex(MANIFEST), {unit.unit_id: entry for unit in units}
    )
    (root / rd.SPAWN_SPLIT_PATH).parent.mkdir(parents=True, exist_ok=True)
    (root / rd.SPAWN_SPLIT_PATH).write_text(artifact, encoding="utf-8")


def run(root: Path, capsys: pytest.CaptureFixture[str], *flags: str):
    code = css.main(["--repo-root", str(root), *flags])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


@pytest.fixture
def plugin(tmp_path: Path) -> Path:
    build_plugin(tmp_path)
    return tmp_path


# -- The figures -------------------------------------------------------------------------


def test_a_unit_is_counted_whole_and_split_with_its_label(plugin, capsys):
    code, out, _ = run(plugin, capsys, "--json")

    figures = json.loads(out)["units"][PROTOCOL.unit_id]
    assert code == 0
    assert figures["whole_chars"] == len(label(PROTOCOL)) + len(KEPT + DROPPED)
    assert figures["split_chars"] == len(label(PROTOCOL)) + len(KEPT)
    assert figures["shed_chars"] == len(DROPPED)


def test_the_total_is_the_sum_over_the_units(plugin, capsys):
    report = json.loads(run(plugin, capsys, "--json")[1])

    total = report["total"]
    units = report["units"].values()
    assert total["whole_chars"] == sum(u["whole_chars"] for u in units)
    assert total["split_chars"] == sum(u["split_chars"] for u in units)
    assert total["shed_chars"] == total["whole_chars"] - total["split_chars"]
    assert report["tokens"]["shed"] == sum(u["tokens"]["shed"] for u in units)


def test_only_units_with_a_stored_split_are_counted(tmp_path, capsys):
    build_plugin(tmp_path, split_units=(INTERMEDIATE,))

    report = json.loads(run(tmp_path, capsys, "--json")[1])

    assert list(report["units"]) == [INTERMEDIATE.unit_id]


def test_a_unit_whose_split_is_distrusted_is_counted_whole_and_named(plugin, capsys):
    (plugin / INTERMEDIATE.path).write_text(
        FRONTMATTER + KEPT + DROPPED + "Edited since the split was cut.\n", encoding="utf-8"
    )

    code, out, err = run(plugin, capsys, "--json")

    figures = json.loads(out)["units"][INTERMEDIATE.unit_id]
    assert (code, figures["shed_chars"]) == (0, 0)
    assert INTERMEDIATE.unit_id in err


# -- The token figure ---------------------------------------------------------------------


def test_the_default_token_figure_is_the_offline_estimate(plugin, capsys, monkeypatch):
    def refuse(*_args, **_kwargs):
        raise AssertionError("the default count made a tokenizer request")

    monkeypatch.setattr(mtb, "count_tokens", refuse)

    code, out, _ = run(plugin, capsys, "--json")

    tokens = json.loads(out)["tokens"]
    assert (code, tokens["basis"]) == (0, "estimate")
    assert tokens["shed"] == tokens["whole"] - tokens["split"] > 0


def test_the_tokenizer_is_used_only_when_asked_and_labelled(plugin, capsys, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(mtb, "count_tokens", lambda text, api_key, *rest: len(text))

    report = json.loads(run(plugin, capsys, "--json", "--tokenizer")[1])

    assert report["tokens"]["basis"] == "tokenizer"
    assert report["units"][PROTOCOL.unit_id]["tokens"]["shed"] == len(
        label(PROTOCOL) + KEPT + DROPPED
    ) - len(label(PROTOCOL) + KEPT)


def test_the_tokenizer_without_a_key_is_an_input_error(plugin, capsys, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    code, out, err = run(plugin, capsys, "--tokenizer")

    assert (code, out) == (2, "")
    assert "ANTHROPIC_API_KEY" in err


def test_an_unreachable_tokenizer_is_an_input_error_not_a_silent_estimate(
    plugin, capsys, monkeypatch
):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(mtb, "count_tokens", lambda *_args, **_kwargs: None)

    code, _, err = run(plugin, capsys, "--tokenizer")

    assert code == 2
    assert "tokenizer" in err


# -- The report ---------------------------------------------------------------------------


def test_plain_output_is_one_line_per_unit_then_the_total(plugin, capsys):
    code, out, _ = run(plugin, capsys)

    lines = out.splitlines()
    assert code == 0
    assert [line.split(":")[0] for line in lines] == [
        PROTOCOL.unit_id,
        INTERMEDIATE.unit_id,
        "total",
    ]
    assert "estimate" in lines[-1]


def test_the_json_report_has_the_contract_shape(plugin, capsys):
    report = json.loads(run(plugin, capsys, "--json")[1])

    assert set(report) == {"schema", "units", "total", "tokens"}
    assert report["schema"] == 1
    assert set(report["units"][PROTOCOL.unit_id]) == {
        "whole_chars",
        "split_chars",
        "shed_chars",
        "tokens",
    }
    assert set(report["total"]) == {"whole_chars", "split_chars", "shed_chars"}
    assert set(report["tokens"]) == {"whole", "split", "shed", "basis"}


# -- Input errors ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "missing",
    [rd.SPAWN_SPLIT_PATH, rd.AUDIENCE_MANIFEST_PATH, PROTOCOL.path],
    ids=["split artifact", "audience manifest", "rule source"],
)
def test_a_missing_input_is_an_input_error_naming_it(plugin, capsys, missing):
    (plugin / missing).unlink()

    code, out, err = run(plugin, capsys)

    assert (code, out) == (2, "")
    assert missing in err


def test_an_unparseable_split_artifact_is_an_input_error(plugin, capsys):
    (plugin / rd.SPAWN_SPLIT_PATH).write_text("{not json", encoding="utf-8")

    code, _, err = run(plugin, capsys)

    assert code == 2
    assert rd.SPAWN_SPLIT_PATH in err
