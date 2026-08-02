"""ComplexipyCollector — Python cognitive complexity via ``uvx complexipy``.

Complexipy is a soft (Tier 1) collector scoped to Python. It is the first
language-specific collector that fully exercises the ``NotApplicable``
resolution outcome: a repository with zero committed ``.py`` files produces
``NotApplicable`` (silent skip, no install hint), while a missing ``uvx``
produces ``Unavailable`` (actionable install hint). The distinction matters
because the MD renderer surfaces the two outcomes differently.

Invocation shape:

* ``resolve()`` first probes ``git ls-files`` to detect whether any ``.py``
  files exist in the committed-file set (untracked files in ``.venv`` etc.
  intentionally do not count). If no ``.py`` files are present, returns
  ``NotApplicable`` before touching ``uvx``. Otherwise, emits the shared
  first-run hint on stderr and probes ``uvx`` with ``shutil.which`` followed
  by ``uvx complexipy --version`` under a 120s deadline.
* ``collect()`` runs ``uvx complexipy <repo_root> --output-json`` and parses
  the flat list of per-function records. Per-file rollups (``max_cognitive``,
  ``p75_cognitive``, ``p95_cognitive``, ``function_count``, ``cognitive_scores``)
  plus a repo-wide aggregate (``cognitive_p95``, ``cognitive_p75``,
  ``total_function_count``) land in the namespace. Empty function set yields
  null percentiles, not zero — zero would collide with "every function is
  trivial", while null unambiguously means "no signal to compute on".

Percentile policy: ``statistics.quantiles(..., method="inclusive")`` from the
standard library, same as the lizard collector. The ``p_nth`` helper is
imported from the shared ``scripts.project_metrics._quantiles`` module (extracted
once the rule-of-two fired on ``lizard_collector.py`` + this one).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from scripts.project_metrics._quantiles import p_nth as _p_nth
from scripts.project_metrics.collectors.base import (
    Available,
    CollectionContext,
    Collector,
    CollectorResult,
    NotApplicable,
    ResolutionEnv,
    ResolutionResult,
    Unavailable,
)

__all__ = ["ComplexipyCollector"]


# ---------------------------------------------------------------------------
# Tunables.
# ---------------------------------------------------------------------------

_RESOLVE_TIMEOUT_SECONDS: float = 120.0
_COLLECT_TIMEOUT_SECONDS: float = 60.0
_FIRST_RUN_HINT: str = (
    "project-metrics: resolving Tier 1 tools (first-run uvx cache fill, may take up to 120s)"
)
_UVX_INSTALL_HINT: str = "install uv: https://docs.astral.sh/uv/"
_UVX_NOT_FOUND_REASON: str = "uvx not found on PATH (complexipy requires uvx to resolve)"
_NOT_APPLICABLE_REASON: str = "No Python source files detected in repository"
_COMPLEXIPY_LANGUAGES: frozenset[str] = frozenset({"python"})


class ComplexipyCollector(Collector):
    """Python cognitive complexity via ``uvx complexipy``."""

    name = "complexipy"
    tier = 1
    required = False
    languages: frozenset[str] = _COMPLEXIPY_LANGUAGES

    def __init__(self, repo_root: Path | str | None = None) -> None:
        """Store the optional repo root; collection time uses ``ctx.repo_root``.

        Kept in parity with ``LizardCollector`` so all Tier 1 collectors share
        a stable constructor signature. ``resolve`` uses the configured root
        when present (for the ``git ls-files`` probe); falls back to ``None``
        which makes ``subprocess.run`` operate in the current working directory.
        """

        self._configured_repo_root: Path | None = Path(repo_root) if repo_root is not None else None

    # ------------------------------------------------------------------ resolve

    def resolve(self, env: ResolutionEnv) -> ResolutionResult:
        """Detect Python applicability, then probe ``uvx complexipy --version``.

        Resolution order: ``git ls-files`` first (cheap and short-circuits
        to ``NotApplicable`` on non-Python repos), then ``uvx`` availability,
        then the version probe. The first-run stderr hint lands only before
        the ``uvx`` probe — no reason to warn the user about cache fills
        before we know we need uvx at all.
        """

        if not _repo_has_python_files(self._configured_repo_root):
            return NotApplicable(reason=_NOT_APPLICABLE_REASON)

        if shutil.which("uvx") is None:
            return Unavailable(
                reason=_UVX_NOT_FOUND_REASON,
                install_hint=_UVX_INSTALL_HINT,
            )

        print(_FIRST_RUN_HINT, file=sys.stderr)

        try:
            completed = subprocess.run(
                ["uvx", "complexipy", "--version"],
                capture_output=True,
                text=True,
                check=True,
                timeout=_RESOLVE_TIMEOUT_SECONDS,
            )
        except FileNotFoundError:
            return Unavailable(
                reason=_UVX_NOT_FOUND_REASON,
                install_hint=_UVX_INSTALL_HINT,
            )
        except subprocess.TimeoutExpired:
            return Unavailable(
                reason=("uvx complexipy first-run cache fill timed out after 120s"),
                install_hint=_UVX_INSTALL_HINT,
            )
        except subprocess.CalledProcessError as exc:
            return Unavailable(
                reason=(f"uvx complexipy --version exited with status {exc.returncode}"),
                install_hint=_UVX_INSTALL_HINT,
            )

        version = _parse_version_output(completed.stdout)
        return Available(version=version)

    # ------------------------------------------------------------------ collect

    def collect(self, ctx: CollectionContext) -> CollectorResult:
        """Run ``uvx complexipy --output-format json`` over ``ctx.repo_root``.

        Invoked inside a scratch cwd so that complexipy's cwd-relative
        side-effect file — a ``complexipy-results.json`` file written next
        to wherever the tool is invoked — lands in a disposable tempdir and
        is swept on scope exit, rather than polluting the project root.
        The repo root is still passed as a positional argument, so the
        scan target is unaffected.

        Modern complexipy writes structured JSON to that side-effect file
        and emits pretty-printed text on stdout; the parser must read the
        file rather than the captured stdout. The ``--output-format json``
        flag replaces the deprecated ``--output-json`` (still accepted by
        current versions but slated for removal).
        """

        # Resolve the scan target to an absolute path BEFORE entering the
        # tempdir-as-cwd context: complexipy interprets relative arguments
        # against the subprocess cwd, and ``ctx.repo_root`` arrives as "."
        # (the runner's convention). Without resolution, complexipy would
        # scan the empty scratch tempdir instead of the project root.
        scan_target = str(Path(ctx.repo_root).resolve())

        with tempfile.TemporaryDirectory(prefix="praxion-complexipy-") as scratch:
            try:
                # ``check=False`` is intentional: complexipy exits non-zero
                # when any analyzed function exceeds its built-in complexity
                # threshold, but the analysis still completes and the
                # results file is still written. We do not care about the
                # threshold judgement -- we want the per-function data.
                # The presence of the results file (verified below) is the
                # real success signal.
                subprocess.run(
                    [
                        "uvx",
                        "complexipy",
                        scan_target,
                        "--output-format",
                        "json",
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=_COLLECT_TIMEOUT_SECONDS,
                    cwd=scratch,
                )
            except subprocess.TimeoutExpired:
                return CollectorResult(
                    status="timeout",
                    data={},
                    issues=[
                        "uvx complexipy --output-format json timed out after "
                        f"{int(_COLLECT_TIMEOUT_SECONDS)}s."
                    ],
                )
            except FileNotFoundError:
                return CollectorResult(
                    status="error",
                    data={},
                    issues=["uvx not found on PATH during collect."],
                )

            results_file = Path(scratch) / "complexipy-results.json"
            if not results_file.is_file():
                return CollectorResult(
                    status="error",
                    data={},
                    issues=[
                        "complexipy did not produce complexipy-results.json "
                        f"at {results_file}; the analysis failed silently or "
                        "the JSON output contract changed."
                    ],
                )
            try:
                results_text = results_file.read_text(encoding="utf-8")
            except OSError as exc:
                return CollectorResult(
                    status="error",
                    data={},
                    issues=[f"failed to read complexipy results file {results_file}: {exc!r}"],
                )

            return _parse_complexipy_json(results_text)


# ---------------------------------------------------------------------------
# Python-file detection — uses ``git ls-files`` so only committed sources count.
# ---------------------------------------------------------------------------


def _repo_has_python_files(repo_root: Path | None) -> bool:
    """Return True when ``git ls-files`` reports at least one ``.py`` entry.

    ``Path.rglob("*.py")`` would include ``.venv/`` and other untracked
    directories, masking a truly non-Python repository. Using the committed
    scope matches the intent of the NotApplicable outcome: we skip when the
    repository's own Python content is zero.

    When ``git ls-files`` itself fails (no git repo, binary missing), assume
    applicability — the uvx branch will fail out and return ``Unavailable``
    with an actionable message, which is more useful than silently reporting
    ``NotApplicable`` for a broken git setup.
    """

    cwd = str(repo_root) if repo_root is not None else None
    try:
        completed = subprocess.run(
            ["git", "ls-files"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
            timeout=_RESOLVE_TIMEOUT_SECONDS,
        )
    except (
        FileNotFoundError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
    ):
        return True

    for line in completed.stdout.splitlines():
        if line.endswith(".py"):
            return True
    return False


# ---------------------------------------------------------------------------
# JSON parsing.
# ---------------------------------------------------------------------------


def _parse_complexipy_json(json_text: str) -> CollectorResult:
    """Parse complexipy's flat per-function JSON into per-file rollups + aggregate.

    Returns ``status='partial'`` when at least one record is malformed
    (missing ``file`` or ``cognitive_complexity``, non-integer value).
    Malformed records are skipped and described in ``issues``; well-formed
    siblings still roll up normally.
    """

    issues: list[str] = []
    try:
        records = json.loads(json_text) if json_text.strip() else []
    except json.JSONDecodeError as exc:
        return CollectorResult(
            status="error",
            data={},
            issues=[f"complexipy JSON is not well-formed: {exc}"],
        )

    if not isinstance(records, list):
        return CollectorResult(
            status="error",
            data={},
            issues=[
                f"complexipy JSON root is not a list of records; got {type(records).__name__}."
            ],
        )

    per_file_scores: dict[str, list[int]] = {}
    all_scores: list[int] = []

    for record in records:
        parsed = _parse_record(record)
        if isinstance(parsed, _RecordError):
            issues.append(parsed.message)
            continue
        file_path, score = parsed
        per_file_scores.setdefault(file_path, []).append(score)
        all_scores.append(score)

    files_block: dict[str, dict[str, Any]] = {}
    for file_path in sorted(per_file_scores):
        scores = per_file_scores[file_path]
        files_block[file_path] = {
            "max_cognitive": max(scores),
            "p75_cognitive": _p_nth(scores, 75),
            "p95_cognitive": _p_nth(scores, 95),
            "function_count": len(scores),
            "cognitive_scores": list(scores),
        }

    aggregate = {
        "cognitive_p95": _p_nth(all_scores, 95),
        "cognitive_p75": _p_nth(all_scores, 75),
        "total_function_count": len(all_scores),
    }

    status = "partial" if issues else "ok"
    return CollectorResult(
        status=status,
        data={"files": files_block, "aggregate": aggregate},
        issues=issues,
    )


class _RecordError:
    """Sentinel for a malformed complexipy record — carries the reason."""

    __slots__ = ("message",)

    def __init__(self, message: str) -> None:
        self.message = message


def _parse_record(record: Any) -> tuple[str, int] | _RecordError:
    """Extract ``(file_path, cognitive_complexity)`` from a single record.

    Modern complexipy emits objects like
    ``{"path": "src/app.py", "file_name": "app.py",
       "function_name": "foo", "complexity": 5}``. Older versions
    used ``"file"`` and ``"cognitive_complexity"``; we tolerate both
    so the collector survives a future complexipy schema flip-back.

    Missing keys, wrong types, or non-integer scores are captured as
    ``_RecordError`` so the caller can record the skip and continue.
    """

    if not isinstance(record, dict):
        return _RecordError(
            f"Skipped malformed complexipy record: expected object, got {type(record).__name__}."
        )

    # Path: prefer ``path`` (modern) then ``file`` (legacy) then
    # ``file_name`` (basename-only fallback).
    file_path = record.get("path") or record.get("file") or record.get("file_name")
    if not isinstance(file_path, str) or not file_path:
        return _RecordError(
            "Skipped malformed complexipy record: missing or non-string "
            f"path/file/file_name field (record={record!r})."
        )

    # Score: prefer ``complexity`` (modern) then ``cognitive_complexity`` (legacy).
    raw_score = record.get("complexity")
    if raw_score is None:
        raw_score = record.get("cognitive_complexity")
    if not isinstance(raw_score, int) or isinstance(raw_score, bool):
        return _RecordError(
            f"Skipped malformed complexipy record for {file_path!r}: "
            f"non-integer complexity={raw_score!r}."
        )

    return file_path, raw_score


# ---------------------------------------------------------------------------
# Version parsing.
# ---------------------------------------------------------------------------


def _parse_version_output(raw: str) -> str:
    """Strip whitespace from ``uvx complexipy --version`` output.

    Complexipy emits ``"complexipy 4.1.0\\n"``-style output. Tests assert
    substring containment of the numeric version, so returning the stripped
    raw output is robust to either "bare version" or "prefix + version" emission.
    """

    return raw.strip()
