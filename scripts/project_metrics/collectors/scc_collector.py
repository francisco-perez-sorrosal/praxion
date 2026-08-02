"""SccCollector — Tier 0 soft-dep SLOC and language-breakdown collector.

``SccCollector`` wraps the external ``scc`` CLI (https://github.com/boyter/scc)
which emits per-language and per-file source-lines-of-code statistics in JSON.
It is a **soft dependency** (``required = False``): when ``scc`` is absent the
runner substitutes the uniform 3-key skip marker into the ``scc`` namespace
and downstream renderers degrade gracefully. Only ``GitCollector`` is the
hard-floor collector.

Payload emitted in ``data`` when available:

* ``language_breakdown`` — dict[language -> {"sloc": int, "file_count": int}]
  per-language rollup derived from the top-level ``scc --format json`` list.
* ``per_file_sloc`` — dict[path -> int] flat mapping of every file's ``Code``
  field. Flat ``dict[str, int]`` is the stable shape the aggregate layer
  reads; nesting would require a second pass in the composition layer.
* ``sloc_total`` — int, the sum of every language's ``Code`` total. Feeds
  the aggregate ``sloc_total`` column.
* ``language_count`` — int, the number of distinct languages detected
  (length of the top-level ``scc`` list).
* ``file_count`` — int, the number of distinct file paths across all
  languages. Feeds the aggregate ``file_count`` column.

The collector is deterministic given a fixed repo state: ``scc`` itself
walks the filesystem in a stable order, and the payload assembly preserves
whatever order ``scc`` emits. Tests assert membership and golden values, not
iteration order, so drift between ``scc`` versions does not break the
contract as long as the JSON keys stay stable.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from scripts.project_metrics._path_filter import (
    filter_path_dict,
    is_excluded_path,
    scc_exclude_dir_args,
)
from scripts.project_metrics.collectors.base import (
    Available,
    CollectionContext,
    Collector,
    CollectorResult,
    ResolutionEnv,
    ResolutionResult,
    Unavailable,
)

__all__ = ["SccCollector"]


# ---------------------------------------------------------------------------
# Tunables — probe and collect timeouts sized to real-world scc invocations.
# Short probe so a hung binary cannot stall the whole report; longer collect
# budget because scc walks the full working tree on large repositories.
# ---------------------------------------------------------------------------

_SCC_PROBE_TIMEOUT_SECONDS: float = 2.0
_SCC_COLLECT_TIMEOUT_SECONDS: float = 60.0

_SCC_INSTALL_HINT: str = (
    "install scc: brew install scc / cargo install scc-go / "
    "go install github.com/boyter/scc/v3@latest"
)


class SccCollector(Collector):
    """Tier 0 soft-dep SLOC and language-breakdown collector (wraps the scc CLI)."""

    name = "scc"
    tier = 0
    required = False
    languages: frozenset[str] = frozenset()

    def __init__(self, repo_root: Path | str | None = None) -> None:
        """Store the repo root used for collection.

        ``None`` defers the decision to collect time: the runner threads
        the authoritative repo root through :attr:`CollectionContext.repo_root`
        regardless. The optional constructor argument matches the
        ``GitCollector`` precedent so registry construction sites can pass
        a repo root uniformly when one is known at wiring time.
        """

        self._configured_repo_root: Path | None = Path(repo_root) if repo_root is not None else None

    # ------------------------------------------------------------------ resolve

    def resolve(self, env: ResolutionEnv) -> ResolutionResult:
        """Probe for the ``scc`` binary and run a short ``scc --version`` check.

        Two-step probe so both the common "not installed" case and the rarer
        race condition (binary vanished between ``which`` and ``run``) map
        uniformly to ``Unavailable`` with actionable install hints — never a
        raised exception that would escape into the runner.
        """

        # env.which() is available for parity with other collectors, but the
        # module-level shutil.which is patched by the test suite, so the
        # direct call is what the contract requires.
        _ = env  # kept for future parity; env-carried PATH isolation unused here
        binary = shutil.which("scc")
        if binary is None:
            return Unavailable(
                reason="scc not found on PATH",
                install_hint=_SCC_INSTALL_HINT,
            )

        try:
            completed = subprocess.run(
                ["scc", "--version"],
                capture_output=True,
                text=True,
                check=False,
                timeout=_SCC_PROBE_TIMEOUT_SECONDS,
            )
        except FileNotFoundError:
            # Race condition: shutil.which returned a path, but the binary
            # vanished before subprocess.run executed. Treat as Unavailable
            # — the net user-facing situation is identical to "not installed".
            return Unavailable(
                reason="scc not found on PATH",
                install_hint=_SCC_INSTALL_HINT,
            )
        except subprocess.TimeoutExpired:
            return Unavailable(
                reason=(f"scc --version probe timed out after {_SCC_PROBE_TIMEOUT_SECONDS}s"),
                install_hint=_SCC_INSTALL_HINT,
            )

        version = _parse_scc_version(completed.stdout)
        return Available(
            version=version,
            details={"binary": binary},
        )

    # ------------------------------------------------------------------ collect

    def collect(self, ctx: CollectionContext) -> CollectorResult:
        """Run ``scc --format json`` over the repo root and parse its output.

        Errors during the subprocess invocation or JSON parsing downgrade to
        ``status='error'`` rather than raising — the runner's try/except is
        a safety net for bugs, not the primary error path.
        """

        # Extend scc's built-in exclusion defaults (.git, .hg, .svn) with our
        # ecosystem-noise list so the underlying tool never even reads those
        # directories. The post-filter pass below catches anything not
        # expressible as a single-component dir name (e.g., .claude/worktrees).
        # ``--by-file`` is required: without it, scc emits per-language
        # aggregates only, the ``Files`` array is empty, and the post-filter
        # pass has nothing to operate on.
        argv = [
            "scc",
            "--format",
            "json",
            "--by-file",
            *scc_exclude_dir_args(),
            ctx.repo_root,
        ]
        try:
            completed = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                check=True,
                timeout=_SCC_COLLECT_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            return CollectorResult(
                status="timeout",
                issues=[f"scc exceeded the {_SCC_COLLECT_TIMEOUT_SECONDS}s collect budget"],
            )
        except (FileNotFoundError, subprocess.CalledProcessError) as exc:
            return CollectorResult(
                status="error",
                issues=[f"scc invocation failed: {exc!r}"],
            )

        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            return CollectorResult(
                status="error",
                issues=[f"scc JSON parse failed: {exc!r}"],
            )

        data = _build_data_payload(payload)
        return CollectorResult(status="ok", data=data)


# ---------------------------------------------------------------------------
# Pure helpers — deterministic transforms from the raw scc payload into the
# namespace-block shape the aggregate and renderer layers consume.
# ---------------------------------------------------------------------------


def _parse_scc_version(stdout: str) -> str:
    """Return ``scc --version`` stripped of its ``scc version `` prefix.

    Mirrors ``GitCollector._resolve_git_version``'s shape so the two
    collectors surface version strings uniformly in ``tool_availability``.
    Falls back to the raw stdout (stripped) when the expected prefix is
    absent — some builds emit only the bare version.
    """

    raw = stdout.strip()
    prefix = "scc version "
    if raw.startswith(prefix):
        return raw[len(prefix) :]
    return raw


def _build_data_payload(payload: Any) -> dict[str, Any]:
    """Assemble the ``data`` dict the runner forwards into the report.

    The input is expected to be a list of per-language dicts (``scc --format
    json`` shape). Defensive: when the payload is not a list, returns an
    empty breakdown rather than raising — the caller still records a
    status='ok' result because the subprocess did succeed; downstream
    composition tolerates empty aggregates.

    Excluded paths (per ``scripts.project_metrics._path_filter``) are
    dropped from ``per_file_sloc`` and the per-language totals are
    recomputed from the kept files. The scc CLI itself is invoked with
    ``--exclude-dir`` so most exclusions never reach this point; this
    pass is defense in depth for multi-component patterns that
    ``--exclude-dir`` cannot express (e.g., ``.claude/worktrees``).
    """

    if not isinstance(payload, list):
        return {
            "language_breakdown": {},
            "per_file_sloc": {},
            "sloc_total": 0,
            "language_count": 0,
            "file_count": 0,
        }

    per_file_sloc: dict[str, int] = {}
    per_file_language: dict[str, str] = {}

    for language_entry in payload:
        if not isinstance(language_entry, dict):
            continue
        language_name = str(language_entry.get("Name", ""))
        files = language_entry.get("Files", [])
        if not isinstance(files, list):
            continue
        for file_entry in files:
            if not isinstance(file_entry, dict):
                continue
            # Prefer ``Location`` (full relative path) over ``Filename``
            # (basename only). Path-filtering and per-file aggregation
            # both need the directory context that ``Location`` carries.
            path = file_entry.get("Location") or file_entry.get("Filename")
            if not isinstance(path, str) or not path:
                continue
            if is_excluded_path(path):
                continue
            per_file_sloc[path] = _safe_int(file_entry.get("Code", 0))
            if language_name:
                per_file_language[path] = language_name

    # Defense in depth — catches anything that bypassed the in-loop check.
    per_file_sloc = filter_path_dict(per_file_sloc)
    per_file_language = filter_path_dict(per_file_language)

    language_breakdown = _rebuild_language_breakdown(per_file_sloc, per_file_language)
    sloc_total = sum(per_file_sloc.values())

    return {
        "language_breakdown": language_breakdown,
        "per_file_sloc": per_file_sloc,
        "sloc_total": sloc_total,
        "language_count": len(language_breakdown),
        "file_count": len(per_file_sloc),
    }


def _rebuild_language_breakdown(
    per_file_sloc: dict[str, int],
    per_file_language: dict[str, str],
) -> dict[str, dict[str, int]]:
    """Sum per-language ``sloc`` and ``file_count`` from the filtered file set.

    Languages whose every file was excluded drop out of the breakdown
    entirely — ``language_count`` therefore reflects languages that
    survived filtering, not what scc originally reported.
    """

    breakdown: dict[str, dict[str, int]] = {}
    for filename, sloc in per_file_sloc.items():
        language = per_file_language.get(filename)
        if not language:
            continue
        entry = breakdown.setdefault(language, {"sloc": 0, "file_count": 0})
        entry["sloc"] += sloc
        entry["file_count"] += 1
    return breakdown


def _safe_int(value: Any) -> int:
    """Coerce ``value`` to int, defaulting to 0 on malformed input.

    scc's JSON fields are integer by contract, but defensive coercion keeps
    the collector from raising on a future schema drift.
    """

    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
