"""Behavioral tests for the ``report_praxion_issue.py`` CLI.

The CLI is a thin argparse wrapper over ``scripts/praxion_feedback/``'s pure
modules (fingerprint, sanitizer, candidate_store, render) -- these tests
exercise the CLI's orchestration and file-system contract, not the modules'
internals (those have their own dedicated test files).

Import strategy -- every test imports ``main`` inside its body (via
``_run_main``), and the subprocess-based plugin-cache tests spawn a real
Python process. During the BDD/TDD RED handshake, ``report_praxion_issue.py``
does not exist yet; deferred imports and subprocess invocation both fail with
a specific error per test rather than collapsing the whole file into one
collection error.

Repo-root strategy -- every test that exercises repo-root resolution builds a
*real*, minimal git repository (``git init`` only, no commit needed since
``git rev-parse --show-toplevel`` resolves the instant a ``.git`` directory
exists) rather than mocking ``subprocess.run``. Git is a guaranteed-present,
fast, deterministic collaborator in this codebase, so exercising the real
``git_toplevel_from_cwd()`` path is a stronger proof of AC10 ("resolves via
git, never ``__file__``") than a mock standing in for it.

The plugin-cache-safety tests mirror ``scripts/test_finalize_adrs.py``'s
``_make_fake_plugin`` / ``TestConsumerLayoutEndToEnd`` pattern exactly -- the
identical ``__file__``-vs-git-root pitfall class, guarded the same way: copy
the real script + package into a directory shaped like an installed-plugin
cache location, then invoke it via a real subprocess against a *separate*
real consumer git repo.

Flag-name assumption (flagged, not invented silently): SYSTEMS_PLAN.md's
Components section names ``--category``, ``--artifact``, ``--error``,
``--detected-by``, ``--detection-point``, ``--confidence`` literally, but
only describes the remaining §5.2 fields as "expected/observed/repro/
environment/regression fields" without spelling out flag names. This suite
assumes the natural hyphenated argparse reading: ``--expected``,
``--observed``, ``--reproduction-command``, ``--environment``,
``--regression-status`` -- mirroring ``candidate_store.py``'s ``_FIELD_ORDER``
keys. If the paired implementer chooses different flag names, only
``_capture_flags`` needs updating (isolated by design).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Real-git-repo + CLI-invocation helpers.
# ---------------------------------------------------------------------------


def _init_git_repo(root: Path) -> None:
    """Initialize a real, minimal git repository at ``root``.

    No commit is required -- ``git rev-parse --show-toplevel`` resolves as
    soon as a ``.git`` directory exists, which is all the CLI's repo-root
    resolution depends on.
    """
    root.mkdir(parents=True, exist_ok=True)
    for args in (
        ["git", "init", "-q"],
        ["git", "config", "user.email", "tester@example.com"],
        ["git", "config", "user.name", "Tester"],
    ):
        subprocess.run(args, cwd=root, check=True, capture_output=True, text=True)


def _capture_flags(**overrides: str) -> dict[str, str]:
    """Minimal, complete flag set for the ``capture`` subcommand.

    Mirrors ``scripts/praxion_feedback/tests/test_candidate_store.py``'s
    ``_candidate_fields`` builder, translated into CLI flag names.
    """
    flags = {
        "--category": "scripts",
        "--artifact": "scripts/praxion_feedback/fingerprint.py",
        "--error": "AttributeError: 'NoneType' object has no attribute 'foo'",
        "--detected-by": "sentinel",
        "--detection-point": "post-implementation audit",
        "--confidence": "high",
        "--expected": "normalize_error strips volatile tokens",
        "--observed": "raises AttributeError on a None error string",
        "--reproduction-command": (
            "python3 -m pytest scripts/praxion_feedback/tests/test_fingerprint.py"
        ),
        "--environment": "macOS, Python 3.11",
        "--regression-status": "new",
    }
    flags.update(overrides)
    return flags


def _capture_argv(**overrides: str) -> list[str]:
    argv = ["capture"]
    for flag, value in _capture_flags(**overrides).items():
        argv.extend([flag, value])
    return argv


def _run_main(argv: list[str]) -> int:
    """Invoke the CLI's ``main`` entry point, imported per-call.

    Deferred import (not a top-of-module import) so RED-first collection
    succeeds before ``report_praxion_issue.py`` exists -- each test fails
    independently with its own ``ModuleNotFoundError`` rather than collapsing
    the whole file into one collection error.
    """
    from scripts.report_praxion_issue import main

    return main(argv)


def _pending_path(repo_root: Path) -> Path:
    return repo_root / ".ai-state" / "praxion_feedback" / "PENDING.md"


def _full_fingerprint_from_pending(pending: Path) -> str:
    match = re.search(r"- fingerprint: ([0-9a-f]{64})", pending.read_text())
    assert match is not None, "expected a stored `- fingerprint: <sha256>` line in PENDING.md"
    return match.group(1)


# ---------------------------------------------------------------------------
# capture: sanitize-at-capture, fingerprinting, dedup.
# ---------------------------------------------------------------------------


class TestCaptureSanitizesAtCapture:
    """A secret-shaped string in the captured error text never reaches disk."""

    def test_a_captured_secret_shaped_string_is_redacted_in_pending_md(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _init_git_repo(tmp_path)
        monkeypatch.chdir(tmp_path)
        secret = "ghp_ABCDEFghijklmnop1234567890abcdef"

        exit_code = _run_main(_capture_argv(**{"--error": f"AuthError: token {secret} rejected"}))

        assert exit_code == 0
        content = _pending_path(tmp_path).read_text()
        assert secret not in content, (
            "sanitize-at-capture must strip a secret-shaped string before it "
            "reaches the git-committed PENDING.md"
        )
        assert "AuthError" in content, "benign surrounding content must survive sanitization"


class TestCaptureAppendsAFingerprintedCandidate:
    def test_capture_appends_a_candidate_carrying_a_sha256_fingerprint(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _init_git_repo(tmp_path)
        monkeypatch.chdir(tmp_path)

        exit_code = _run_main(_capture_argv())

        assert exit_code == 0
        content = _pending_path(tmp_path).read_text()
        assert re.search(r"- fingerprint: [0-9a-f]{64}", content), (
            "capture must write a full sha256 fingerprint line"
        )
        assert "status: pending" in content


class TestCaptureDedupsIdenticalDefects:
    def test_capturing_the_same_defect_twice_yields_exactly_one_candidate(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _init_git_repo(tmp_path)
        monkeypatch.chdir(tmp_path)

        first_exit = _run_main(_capture_argv())
        second_exit = _run_main(_capture_argv())

        assert first_exit == 0
        assert second_exit == 0, "a dedup no-op must not be treated as a CLI failure"
        content = _pending_path(tmp_path).read_text()
        assert len(re.findall(r"^### ", content, re.MULTILINE)) == 1, (
            "capturing an identical (category, artifact, error) twice must "
            "append exactly one candidate block, not two"
        )


# ---------------------------------------------------------------------------
# list: prints pending candidates, drops filed ones.
# ---------------------------------------------------------------------------


class TestListPrintsPendingCandidates:
    def test_list_prints_the_pending_candidates_short_fingerprint(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _init_git_repo(tmp_path)
        monkeypatch.chdir(tmp_path)
        _run_main(_capture_argv())
        pending = _pending_path(tmp_path)
        fingerprint = _full_fingerprint_from_pending(pending)
        capsys.readouterr()  # discard capture's own stdout

        exit_code = _run_main(["list"])

        out = capsys.readouterr().out
        assert exit_code == 0
        assert fingerprint[:8] in out, "list must surface the pending candidate's fingerprint"

    def test_a_filed_candidate_no_longer_appears_in_list_output(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _init_git_repo(tmp_path)
        monkeypatch.chdir(tmp_path)
        _run_main(_capture_argv())
        pending = _pending_path(tmp_path)
        fingerprint = _full_fingerprint_from_pending(pending)
        issue_url = "https://github.com/francisco-perez-sorrosal/praxion/issues/99"
        _run_main(["mark-filed", "--fingerprint", fingerprint, "--issue-url", issue_url])
        capsys.readouterr()

        _run_main(["list"])

        out = capsys.readouterr().out
        assert fingerprint[:8] not in out, "list must never re-surface a filed candidate"


# ---------------------------------------------------------------------------
# render: projects the §5.2 markdown body for a candidate.
# ---------------------------------------------------------------------------


class TestRenderEmitsTheSchemaBody:
    def test_render_emits_all_eight_headings_to_stdout(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from scripts.praxion_feedback.render import SECTION_HEADINGS

        _init_git_repo(tmp_path)
        monkeypatch.chdir(tmp_path)
        _run_main(_capture_argv())
        fingerprint = _full_fingerprint_from_pending(_pending_path(tmp_path))
        capsys.readouterr()

        exit_code = _run_main(["render", "--fingerprint", fingerprint])

        out = capsys.readouterr().out
        assert exit_code == 0
        for heading in SECTION_HEADINGS:
            assert f"## {heading}" in out, f"rendered body missing heading: {heading!r}"

    def test_render_writes_the_body_to_a_body_file_when_requested(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _init_git_repo(tmp_path)
        monkeypatch.chdir(tmp_path)
        _run_main(_capture_argv())
        fingerprint = _full_fingerprint_from_pending(_pending_path(tmp_path))
        body_file = tmp_path / "body.md"

        exit_code = _run_main(
            ["render", "--fingerprint", fingerprint, "--body-file", str(body_file)]
        )

        assert exit_code == 0
        assert "## Fingerprint" in body_file.read_text()


# ---------------------------------------------------------------------------
# mark-filed: moves a candidate out of the pending set.
# ---------------------------------------------------------------------------


class TestMarkFiledMovesCandidateOutOfPending:
    def test_mark_filed_flips_status_and_records_the_issue_url(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _init_git_repo(tmp_path)
        monkeypatch.chdir(tmp_path)
        _run_main(_capture_argv())
        pending = _pending_path(tmp_path)
        fingerprint = _full_fingerprint_from_pending(pending)
        issue_url = "https://github.com/francisco-perez-sorrosal/praxion/issues/99"

        exit_code = _run_main(
            ["mark-filed", "--fingerprint", fingerprint, "--issue-url", issue_url]
        )

        assert exit_code == 0
        content = pending.read_text()
        assert "status: filed" in content
        assert issue_url in content


# ---------------------------------------------------------------------------
# git-root resolution: never __file__, works from a subdir, refuses to
# silently fall back into a plugin-cache-shaped location.
# ---------------------------------------------------------------------------


class TestGitRootResolutionFromASubdirectory:
    def test_capture_invoked_from_a_nested_subdir_still_writes_under_the_repo_root(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _init_git_repo(tmp_path)
        subdir = tmp_path / "some" / "nested" / "dir"
        subdir.mkdir(parents=True)
        monkeypatch.chdir(subdir)

        exit_code = _run_main(_capture_argv())

        assert exit_code == 0
        assert _pending_path(tmp_path).exists(), (
            "capture invoked from a subdirectory of the git worktree must "
            "still resolve and write under the repo root, not the subdir"
        )


def _copy_reporter_into_fake_plugin_cache(base: Path) -> Path:
    """Copy the reporter CLI + its package into a plugin-cache-shaped tree.

    Mirrors ``scripts/test_finalize_adrs.py``'s ``_make_fake_plugin`` for the
    identical pitfall class: Claude Code installs plugins under
    ``.../plugins/cache/<owner>/<plugin>/<ver>``, and a script located there
    must never resolve its consumer's root via its own ``__file__``.
    """
    plugin_scripts = (
        base / "plugins" / "cache" / "francisco-perez-sorrosal" / "praxion" / "v1" / "scripts"
    )
    plugin_scripts.mkdir(parents=True)
    src_scripts = Path(__file__).resolve().parent
    shutil.copy2(
        src_scripts / "report_praxion_issue.py", plugin_scripts / "report_praxion_issue.py"
    )
    shutil.copy2(src_scripts / "_repo_root.py", plugin_scripts / "_repo_root.py")
    shutil.copytree(
        src_scripts / "praxion_feedback",
        plugin_scripts / "praxion_feedback",
        ignore=shutil.ignore_patterns("tests", "__pycache__"),
    )
    return plugin_scripts / "report_praxion_issue.py"


class TestPluginCacheSafeRootResolution:
    """Regression guard for the exact pitfall class ``test_finalize_adrs.py``
    already guards: a script invoked from a symlinked plugin cache must
    resolve the *consumer* repo root via git, never via its own ``__file__``
    location.
    """

    def test_capture_from_a_plugin_cache_location_writes_to_the_consumer_repo(
        self, tmp_path: Path
    ) -> None:
        consumer = tmp_path / "consumer"
        _init_git_repo(consumer)
        fake_script = _copy_reporter_into_fake_plugin_cache(tmp_path)
        plugin_root = fake_script.parent.parent  # .../v1

        result = subprocess.run(
            [sys.executable, str(fake_script), *_capture_argv()],
            cwd=str(consumer),
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": str(fake_script.parent.parent)},
        )

        assert result.returncode == 0, result.stderr
        assert _pending_path(consumer).exists(), (
            "capture from a plugin-cache-shaped location must still write to "
            f"the consumer repo; stderr={result.stderr!r}"
        )
        assert not (plugin_root / ".ai-state").exists(), (
            "capture must never write into the plugin-cache location itself "
            "-- that is the exact __file__-based misresolution being guarded"
        )

    def test_git_resolution_failure_refuses_to_fall_back_into_the_plugin_cache(
        self, tmp_path: Path
    ) -> None:
        """When git-root resolution fails entirely (cwd is not a git working
        tree), the reporter must not silently fall back to writing at its own
        plugin-cache-shaped script location -- it must refuse instead.
        """
        non_git_cwd = tmp_path / "not_a_repo"
        non_git_cwd.mkdir()
        fake_script = _copy_reporter_into_fake_plugin_cache(tmp_path)
        plugin_root = fake_script.parent.parent

        result = subprocess.run(
            [sys.executable, str(fake_script), *_capture_argv()],
            cwd=str(non_git_cwd),
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": str(fake_script.parent.parent)},
        )

        assert result.returncode != 0, (
            "the reporter must refuse rather than silently write into a "
            f"plugin-cache-shaped fallback location; stdout={result.stdout!r}"
        )
        assert not (plugin_root / ".ai-state").exists(), (
            "a refused run must not have written anything under the plugin cache"
        )


# ---------------------------------------------------------------------------
# Plain-file invocation: the wrapper must bootstrap its own import path,
# never rely on the caller's sys.path / PYTHONPATH.
# ---------------------------------------------------------------------------


class TestPlainFileInvocationBootstrapsItsOwnImportPath:
    """Regression guard for a real dogfood failure: running the wrapper as a
    plain file (``python3 scripts/report_praxion_issue.py --help``) from a cwd
    other than the repo root, with no ``PYTHONPATH`` set by the caller, raised
    ``ModuleNotFoundError: No module named 'scripts'`` -- the wrapper's
    absolute ``from scripts.praxion_feedback.cli import main`` relied on the
    caller's ``sys.path``/``PYTHONPATH`` rather than bootstrapping its own.
    pytest's own ``pythonpath = ["."]`` config hid this in every test above,
    since collection always runs from the repo root.

    Distinct from ``TestPluginCacheSafeRootResolution`` above: this is
    "import your own package via ``__file__``" (a legitimate, required use of
    ``__file__``), not the forbidden "resolve the CONSUMER repo root via
    ``__file__``" pitfall -- the two must not be conflated.
    """

    def test_help_succeeds_from_a_non_repo_cwd_with_pythonpath_removed(
        self, tmp_path: Path
    ) -> None:
        wrapper = Path(__file__).resolve().parent / "report_praxion_issue.py"
        clean_env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}

        result = subprocess.run(
            [sys.executable, str(wrapper), "--help"],
            cwd=str(tmp_path),
            capture_output=True,
            text=True,
            env=clean_env,
        )

        assert result.returncode == 0, (
            "the wrapper must bootstrap its own import path rather than rely "
            f"on the caller's sys.path/PYTHONPATH; stderr={result.stderr!r}"
        )
        assert "usage" in result.stdout.lower()

    def test_subcommand_help_succeeds_from_an_unrelated_cwd(self, tmp_path: Path) -> None:
        """A second cwd, with a subcommand that needs no git (``capture
        --help`` short-circuits inside argparse before any repo-root
        resolution), confirms the import bootstrap is cwd-independent on its
        own -- distinct from the CONSUMER-root git resolution (tested above),
        which correctly still requires a real git repo.
        """
        wrapper = Path(__file__).resolve().parent / "report_praxion_issue.py"
        clean_env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
        unrelated_cwd = tmp_path / "not_a_repo_either"
        unrelated_cwd.mkdir()

        result = subprocess.run(
            [sys.executable, str(wrapper), "capture", "--help"],
            cwd=str(unrelated_cwd),
            capture_output=True,
            text=True,
            env=clean_env,
        )

        assert result.returncode == 0, (
            f"`capture --help` must not require a git repo; stderr={result.stderr!r}"
        )
        assert "usage" in result.stdout.lower()
