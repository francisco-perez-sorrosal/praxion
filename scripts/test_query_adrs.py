"""Tests for query_adrs.py -- the read-only, token-free ADR retrieval tool.

Uses synthetic ADR files under `tmp_path` throughout -- never the real corpus
(the smoke run against the real corpus is a manual step in the implementer's
report, not a pytest case, since the corpus's content is not this test's
contract to pin).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import query_adrs

FRONTMATTER = """---
id: {id}
title: {title}
status: {status}
category: {category}
date: "{date}"
summary: {summary}
tags: [{tags}]
made_by: agent
affected_files: [{affected_files}]
---

# Body
"""


def _write_adr(
    decisions_dir: Path,
    filename: str,
    *,
    adr_id: str,
    title: str = "A decision",
    status: str = "accepted",
    category: str = "architectural",
    date: str = "2026-01-01",
    summary: str = "a summary",
    tags: list[str] | None = None,
    affected_files: list[str] | None = None,
    superseded_in_part_by: list[str] | None = None,
) -> Path:
    decisions_dir.mkdir(parents=True, exist_ok=True)
    body = FRONTMATTER.format(
        id=adr_id,
        title=title,
        status=status,
        category=category,
        date=date,
        summary=summary,
        tags=", ".join(tags or []),
        affected_files=", ".join(f'"{f}"' for f in (affected_files or [])),
    )
    if superseded_in_part_by:
        narrowing_list = ", ".join(f'"{n}"' for n in superseded_in_part_by)
        # Inserted before the closing frontmatter fence -- appended, never
        # interleaved, so every other field's position stays stable across
        # tests that don't care about narrowing.
        body = body.replace(
            "---\n\n# Body\n",
            f"superseded_in_part_by: [{narrowing_list}]\n---\n\n# Body\n",
        )
    path = decisions_dir / filename
    path.write_text(body, encoding="utf-8")
    return path


def _write_adr_without_category(decisions_dir: Path, filename: str, *, adr_id: str) -> Path:
    """An ADR authored before `category` existed -- no `category:` line at all."""
    decisions_dir.mkdir(parents=True, exist_ok=True)
    raw = (
        "---\n"
        f"id: {adr_id}\n"
        "title: A decision\n"
        "status: accepted\n"
        'date: "2026-01-01"\n'
        "summary: a summary\n"
        "tags: [x]\n"
        "affected_files: []\n"
        "---\n\n# Body\n"
    )
    path = decisions_dir / filename
    path.write_text(raw, encoding="utf-8")
    return path


@pytest.fixture
def decisions_dir(tmp_path: Path) -> Path:
    return tmp_path / ".ai-state" / "decisions"


# -- Path intersection --------------------------------------------------------


def test_paths_match_exact():
    assert query_adrs.paths_match("skills/foo/SKILL.md", "skills/foo/SKILL.md")


def test_paths_match_dir_prefix_query_is_directory():
    assert query_adrs.paths_match("skills/foo/", "skills/foo/SKILL.md")


def test_paths_match_dir_prefix_entry_is_directory():
    assert query_adrs.paths_match("skills/foo/SKILL.md", "skills/foo/")


def test_paths_match_rejects_sibling_prefix_collision():
    # "skills/foo" must not falsely match "skills/foobar/x" -- no separator boundary.
    assert not query_adrs.paths_match("skills/foo", "skills/foobar/x")
    assert not query_adrs.paths_match("skills/foobar/x", "skills/foo")


def test_paths_match_non_match():
    assert not query_adrs.paths_match("skills/bar/SKILL.md", "skills/foo/SKILL.md")


def test_cli_paths_selector_finds_intersecting_adr(decisions_dir, capsys):
    _write_adr(decisions_dir, "001-a.md", adr_id="dec-001", affected_files=["skills/foo/SKILL.md"])
    _write_adr(decisions_dir, "002-b.md", adr_id="dec-002", affected_files=["skills/bar/SKILL.md"])

    exit_code = query_adrs.main(
        ["--paths", "skills/foo/", "--repo-root", str(decisions_dir.parent.parent)]
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "dec-001" in out
    assert "dec-002" not in out


# -- Status default vs --all ---------------------------------------------------


def test_default_view_excludes_superseded(decisions_dir, capsys):
    _write_adr(decisions_dir, "001-a.md", adr_id="dec-001", status="accepted", tags=["x"])
    _write_adr(decisions_dir, "002-b.md", adr_id="dec-002", status="superseded", tags=["x"])

    exit_code = query_adrs.main(["--tags", "x", "--repo-root", str(decisions_dir.parent.parent)])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "dec-001" in out
    assert "dec-002" not in out


def test_all_flag_includes_superseded(decisions_dir, capsys):
    _write_adr(decisions_dir, "001-a.md", adr_id="dec-001", status="accepted", tags=["x"])
    _write_adr(decisions_dir, "002-b.md", adr_id="dec-002", status="superseded", tags=["x"])

    exit_code = query_adrs.main(
        ["--tags", "x", "--all", "--repo-root", str(decisions_dir.parent.parent)]
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "dec-001" in out
    assert "dec-002" in out


def test_re_affirmation_status_is_in_default_view(decisions_dir, capsys):
    _write_adr(decisions_dir, "001-a.md", adr_id="dec-001", status="re-affirmation", tags=["x"])

    exit_code = query_adrs.main(["--tags", "x", "--repo-root", str(decisions_dir.parent.parent)])

    assert exit_code == 0
    assert "dec-001" in capsys.readouterr().out


# -- Tags -----------------------------------------------------------------


def test_tags_case_insensitive_membership(decisions_dir, capsys):
    _write_adr(decisions_dir, "001-a.md", adr_id="dec-001", tags=["Observability", "Testing"])

    exit_code = query_adrs.main(
        ["--tags", "observability", "--repo-root", str(decisions_dir.parent.parent)]
    )

    assert exit_code == 0
    assert "dec-001" in capsys.readouterr().out


def test_tags_no_membership_is_zero_matches(decisions_dir, capsys):
    _write_adr(decisions_dir, "001-a.md", adr_id="dec-001", tags=["testing"])

    exit_code = query_adrs.main(
        ["--tags", "observability", "--repo-root", str(decisions_dir.parent.parent)]
    )

    assert exit_code == 1


# -- Grep -------------------------------------------------------------------


def test_grep_matches_title_case_insensitive(decisions_dir, capsys):
    _write_adr(
        decisions_dir, "001-a.md", adr_id="dec-001", title="Remove in-house memory subsystem"
    )

    exit_code = query_adrs.main(
        ["--grep", "MEMORY SUBSYSTEM", "--repo-root", str(decisions_dir.parent.parent)]
    )

    assert exit_code == 0
    assert "dec-001" in capsys.readouterr().out


def test_grep_matches_summary(decisions_dir, capsys):
    _write_adr(decisions_dir, "001-a.md", adr_id="dec-001", summary="uses postgres for persistence")

    exit_code = query_adrs.main(
        ["--grep", "postgres", "--repo-root", str(decisions_dir.parent.parent)]
    )

    assert exit_code == 0
    assert "dec-001" in capsys.readouterr().out


def test_grep_invalid_regex_exits_2(decisions_dir, capsys):
    exit_code = query_adrs.main(
        ["--grep", "(unclosed", "--repo-root", str(decisions_dir.parent.parent)]
    )

    assert exit_code == 2


# -- Drafts inclusion -----------------------------------------------------


def test_drafts_directory_is_scanned(decisions_dir, capsys):
    drafts_dir = decisions_dir / "drafts"
    _write_adr(
        drafts_dir,
        "20260830-1200-fps-main-my-slug.md",
        adr_id="dec-draft-abc12345",
        status="proposed",
        tags=["x"],
    )
    # proposed status only surfaces with --all -- drafts do exist mid-pipeline
    # at status: proposed, so this exercises both "drafts are scanned" and
    # the default-status filter together.
    exit_code = query_adrs.main(
        ["--tags", "x", "--all", "--repo-root", str(decisions_dir.parent.parent)]
    )

    assert exit_code == 0
    assert "dec-draft-abc12345" in capsys.readouterr().out


# -- Combined AND filters ---------------------------------------------------


def test_combined_filters_require_all_to_match(decisions_dir, capsys):
    _write_adr(
        decisions_dir,
        "001-a.md",
        adr_id="dec-001",
        tags=["api"],
        affected_files=["skills/foo/SKILL.md"],
    )
    _write_adr(
        decisions_dir,
        "002-b.md",
        adr_id="dec-002",
        tags=["api"],
        affected_files=["skills/bar/SKILL.md"],
    )
    _write_adr(
        decisions_dir,
        "003-c.md",
        adr_id="dec-003",
        tags=["testing"],
        affected_files=["skills/foo/SKILL.md"],
    )

    exit_code = query_adrs.main(
        [
            "--paths",
            "skills/foo/",
            "--tags",
            "api",
            "--repo-root",
            str(decisions_dir.parent.parent),
        ]
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "dec-001" in out
    assert "dec-002" not in out
    assert "dec-003" not in out


# -- Exit codes ---------------------------------------------------------------


def test_no_selector_exits_2(decisions_dir, capsys):
    exit_code = query_adrs.main(["--repo-root", str(decisions_dir.parent.parent)])
    assert exit_code == 2


def test_zero_matches_exits_1(decisions_dir, capsys):
    _write_adr(decisions_dir, "001-a.md", adr_id="dec-001", tags=["x"])
    exit_code = query_adrs.main(["--tags", "nope", "--repo-root", str(decisions_dir.parent.parent)])
    assert exit_code == 1


def test_at_least_one_match_exits_0(decisions_dir):
    _write_adr(decisions_dir, "001-a.md", adr_id="dec-001", tags=["x"])
    exit_code = query_adrs.main(["--tags", "x", "--repo-root", str(decisions_dir.parent.parent)])
    assert exit_code == 0


# -- TSV format ---------------------------------------------------------------


def test_tsv_format_has_no_decoration(decisions_dir, capsys):
    _write_adr(decisions_dir, "001-a.md", adr_id="dec-001", title="A title", tags=["x"])

    exit_code = query_adrs.main(
        ["--tags", "x", "--format", "tsv", "--repo-root", str(decisions_dir.parent.parent)]
    )

    assert exit_code == 0
    out = capsys.readouterr().out.strip()
    assert out == "dec-001\taccepted\tA title\t.ai-state/decisions/001-a.md"


# -- Staged ---------------------------------------------------------------


def test_staged_derives_query_paths_from_git_diff(tmp_path: Path, capsys):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.email", "t@t.t"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.name", "t"], check=True, capture_output=True
    )
    (tmp_path / "skills").mkdir()
    (tmp_path / "skills" / "foo.py").write_text("x", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "-qm", "seed"], check=True, capture_output=True
    )
    # Stage a modification so `git diff --cached` reports it.
    (tmp_path / "skills" / "foo.py").write_text("y", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True, capture_output=True)

    decisions_dir = tmp_path / ".ai-state" / "decisions"
    _write_adr(decisions_dir, "001-a.md", adr_id="dec-001", affected_files=["skills/foo.py"])

    exit_code = query_adrs.main(["--staged", "--repo-root", str(tmp_path)])

    assert exit_code == 0
    assert "dec-001" in capsys.readouterr().out


# -- YAML-fallback parser ------------------------------------------------------


def test_fallback_parser_handles_block_and_inline_lists():
    raw = (
        'id: dec-001\ntitle: A decision\nstatus: accepted\ndate: "2026-01-01"\n'
        "summary: a summary\ntags:\n  - a\n  - b\n"
        'affected_files: ["skills/foo.py", "skills/bar.py"]\n'
    )
    data = query_adrs._parse_frontmatter_fallback(raw, Path("adr.md"))

    assert data["id"] == "dec-001"
    assert data["tags"] == ["a", "b"]
    assert data["affected_files"] == ["skills/foo.py", "skills/bar.py"]


def test_fallback_parser_gives_up_honestly_on_confusing_input(capsys):
    # A stray continuation line that is neither `key: value` nor a `- item`
    # under an open block -- the fallback must skip, not guess.
    raw = "id: dec-001\ntitle: A decision\n  this is not a valid line\n"
    data = query_adrs._parse_frontmatter_fallback(raw, Path("adr.md"))

    assert data is None
    assert "could not parse" in capsys.readouterr().err


def test_load_adr_uses_fallback_when_yaml_unavailable(decisions_dir, monkeypatch):
    path = _write_adr(decisions_dir, "001-a.md", adr_id="dec-001", tags=["x", "y"])

    record = query_adrs.load_adr(path, decisions_dir.parent.parent, yaml_module=None)

    assert record is not None
    assert record.id == "dec-001"
    assert record.tags == ("x", "y")


def test_cli_runs_end_to_end_with_yaml_forced_unavailable(decisions_dir, monkeypatch, capsys):
    _write_adr(decisions_dir, "001-a.md", adr_id="dec-001", tags=["x"])
    monkeypatch.setattr(query_adrs, "_try_import_yaml", lambda: None)

    exit_code = query_adrs.main(["--tags", "x", "--repo-root", str(decisions_dir.parent.parent)])

    assert exit_code == 0
    assert "dec-001" in capsys.readouterr().out


# -- Category field ----------------------------------------------------------


def test_category_loads_under_pyyaml_parser(decisions_dir):
    yaml_module = query_adrs._try_import_yaml()
    if yaml_module is None:
        pytest.skip("PyYAML not installed in this environment")
    path = _write_adr(decisions_dir, "001-a.md", adr_id="dec-001", category="behavioral")

    record = query_adrs.load_adr(path, decisions_dir.parent.parent, yaml_module=yaml_module)

    assert record is not None
    assert record.category == "behavioral"


def test_category_loads_under_stdlib_fallback_parser(decisions_dir):
    path = _write_adr(decisions_dir, "001-a.md", adr_id="dec-001", category="implementation")

    record = query_adrs.load_adr(path, decisions_dir.parent.parent, yaml_module=None)

    assert record is not None
    assert record.category == "implementation"


def test_category_missing_yields_defined_sentinel_under_stdlib_fallback(decisions_dir):
    # A record missing `category` (authored before the field existed) must not
    # raise -- it yields the same "" sentinel every other optional str field
    # (summary, date) already uses for an absent key.
    path = _write_adr_without_category(decisions_dir, "001-a.md", adr_id="dec-001")

    record = query_adrs.load_adr(path, decisions_dir.parent.parent, yaml_module=None)

    assert record is not None
    assert record.category == ""


def test_category_missing_yields_defined_sentinel_under_pyyaml(decisions_dir):
    yaml_module = query_adrs._try_import_yaml()
    if yaml_module is None:
        pytest.skip("PyYAML not installed in this environment")
    path = _write_adr_without_category(decisions_dir, "001-a.md", adr_id="dec-001")

    record = query_adrs.load_adr(path, decisions_dir.parent.parent, yaml_module=yaml_module)

    assert record is not None
    assert record.category == ""


def test_cli_text_output_unchanged_by_category_field(decisions_dir, capsys):
    # No CLI behaviour change from Step 2 -- category is loaded, not displayed.
    _write_adr(
        decisions_dir,
        "001-a.md",
        adr_id="dec-001",
        title="A title",
        tags=["x"],
        category="behavioral",
    )

    exit_code = query_adrs.main(["--tags", "x", "--repo-root", str(decisions_dir.parent.parent)])

    assert exit_code == 0
    assert "category" not in capsys.readouterr().out.lower()


def test_cli_tsv_output_unchanged_by_category_field(decisions_dir, capsys):
    _write_adr(
        decisions_dir,
        "001-a.md",
        adr_id="dec-001",
        title="A title",
        tags=["x"],
        category="behavioral",
    )

    exit_code = query_adrs.main(
        ["--tags", "x", "--format", "tsv", "--repo-root", str(decisions_dir.parent.parent)]
    )

    assert exit_code == 0
    out = capsys.readouterr().out.strip()
    assert out == "dec-001\taccepted\tA title\t.ai-state/decisions/001-a.md"


# -- Sibling-script importability --------------------------------------------


def test_loader_symbols_importable_by_sibling_script_without_side_effects(tmp_path: Path):
    """`load_adr`, `discover_adr_files`, `resolve_repo_root` must be usable
    from another script via a plain `import query_adrs` -- no filesystem
    access, no stdout/stderr output, at import time.
    """
    scripts_dir = str(Path(__file__).resolve().parent)
    probe = tmp_path / "sibling_probe.py"
    probe.write_text(
        "import sys\n"
        f"sys.path.insert(0, {scripts_dir!r})\n"
        "import query_adrs\n"
        "assert callable(query_adrs.load_adr)\n"
        "assert callable(query_adrs.discover_adr_files)\n"
        "assert callable(query_adrs.resolve_repo_root)\n"
        "print('OK')\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(probe)], capture_output=True, text=True, check=False
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "OK"


# -- Help / usage -----------------------------------------------------------


def test_help_exits_0(capsys):
    with pytest.raises(SystemExit) as exc_info:
        query_adrs.main(["--help"])
    assert exc_info.value.code == 0
    assert "EXAMPLES" in capsys.readouterr().out


# -- Narrowing caveat (superseded_in_part_by) ---------------------------------


def test_narrowed_record_stays_in_default_view_with_caveat(decisions_dir, capsys):
    # A record carrying `superseded_in_part_by` is a live, narrowed decision --
    # it must still surface under the default (non-`--all`) status view, with
    # a caveat naming the narrowing id, not silently disappear the way a
    # naive `DEFAULT_STATUSES` exclusion would hide it.
    _write_adr(
        decisions_dir,
        "203-narrowed.md",
        adr_id="dec-203",
        status="accepted",
        tags=["x"],
        superseded_in_part_by=["dec-328"],
    )

    exit_code = query_adrs.main(["--tags", "x", "--repo-root", str(decisions_dir.parent.parent)])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "dec-203" in out
    assert "dec-328" in out


def test_record_without_narrowing_field_carries_no_caveat(decisions_dir, capsys):
    _write_adr(decisions_dir, "001-a.md", adr_id="dec-001", status="accepted", tags=["x"])

    exit_code = query_adrs.main(["--tags", "x", "--repo-root", str(decisions_dir.parent.parent)])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "dec-001" in out
    assert "narrowed" not in out.lower()


def test_narrowing_caveat_present_in_tsv_output(decisions_dir, capsys):
    _write_adr(
        decisions_dir,
        "203-narrowed.md",
        adr_id="dec-203",
        status="accepted",
        title="A narrowed decision",
        tags=["x"],
        superseded_in_part_by=["dec-328"],
    )

    exit_code = query_adrs.main(
        ["--tags", "x", "--format", "tsv", "--repo-root", str(decisions_dir.parent.parent)]
    )

    assert exit_code == 0
    out = capsys.readouterr().out.strip()
    # tsv is decoration-free per its contract (test_tsv_format_has_no_decoration) --
    # the caveat must still be present as data, naming the narrowing id, without
    # introducing a stray extra column that breaks existing tsv consumers'
    # fixed-width parsing.
    assert "dec-328" in out
    fields = out.split("\t")
    assert fields[0] == "dec-203"


def test_narrowing_caveat_unaffected_record_tsv_matches_pre_change_shape(decisions_dir, capsys):
    # Non-regression: a record with no narrowing field keeps the exact
    # 4-column tsv shape asserted by test_tsv_format_has_no_decoration.
    _write_adr(decisions_dir, "001-a.md", adr_id="dec-001", title="A title", tags=["x"])

    exit_code = query_adrs.main(
        ["--tags", "x", "--format", "tsv", "--repo-root", str(decisions_dir.parent.parent)]
    )

    assert exit_code == 0
    out = capsys.readouterr().out.strip()
    assert out == "dec-001\taccepted\tA title\t.ai-state/decisions/001-a.md"


def test_all_flag_still_shows_narrowing_caveat(decisions_dir, capsys):
    # --all's status expansion and the narrowing caveat are independent
    # concerns -- a record reachable only via --all must still carry the
    # caveat when it also carries superseded_in_part_by.
    _write_adr(
        decisions_dir,
        "203-narrowed.md",
        adr_id="dec-203",
        status="superseded",  # old, incorrect encoding -- reachable via --all only
        tags=["x"],
        superseded_in_part_by=["dec-328"],
    )

    exit_code = query_adrs.main(
        ["--tags", "x", "--all", "--repo-root", str(decisions_dir.parent.parent)]
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "dec-203" in out
    assert "dec-328" in out
