"""LizardCollector — cross-language cyclomatic complexity via ``uvx lizard``.

Lizard is a soft (Tier 1) collector: its absence must not fail the run. The
runner skips the namespace with a uniform skip marker when resolution reports
Unavailable, so the aggregate ``ccn_p95`` column renders as null in that case.

Invocation shape:

* ``resolve()`` emits a one-line first-run hint on stderr before the probe
  (``uvx`` may block while fetching lizard into its cache on first use), then
  probes for ``uvx`` with ``shutil.which`` and runs ``uvx lizard --version``
  with a 120s deadline.
* ``collect()`` runs ``uvx lizard --xml <repo_root>`` and parses the CheckStyle
  ``cppncss`` output. Per-file rollups (``max_ccn``, ``p75_ccn``, ``p95_ccn``,
  ``function_count``) plus a repo-wide aggregate (``ccn_p95``) land in the
  namespace. A malformed ``<item>`` is isolated: the record is skipped, the
  issue is appended to ``issues``, and the run downgrades to ``partial``.

Percentile policy: ``statistics.quantiles(..., method="inclusive")`` from the
standard library. Inclusive never exceeds ``max(data)``, which matches user
intuition for discrete integer CCN values. Empty data returns ``None`` (null
in JSON) rather than ``0`` so "no signal" is distinguishable from "trivial
one-liners only".
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from scripts.project_metrics._quantiles import p_nth as _p_nth
from scripts.project_metrics.collectors.base import (
    Available,
    CollectionContext,
    Collector,
    CollectorResult,
    ResolutionEnv,
    ResolutionResult,
    Unavailable,
)

__all__ = ["LizardCollector"]


# ---------------------------------------------------------------------------
# Tunables.
# ---------------------------------------------------------------------------

_RESOLVE_TIMEOUT_SECONDS: float = 120.0
_COLLECT_TIMEOUT_SECONDS: float = 60.0
_FIRST_RUN_HINT: str = (
    "project-metrics: resolving Tier 1 tools "
    "(first-run uvx cache fill, may take up to 120s)"
)
_UVX_INSTALL_HINT: str = "install uv: https://docs.astral.sh/uv/"
_UVX_NOT_FOUND_REASON: str = "uvx not found on PATH (lizard requires uvx to resolve)"
_ITEM_NAME_LOCATION_RE: re.Pattern[str] = re.compile(r" at (.+):(\d+)$")

# Lizard's broadly-advertised language coverage. The exact list is not
# contractually pinned; a non-empty frozenset is the only shape requirement.
_LIZARD_LANGUAGES: frozenset[str] = frozenset(
    {
        "python",
        "javascript",
        "typescript",
        "java",
        "c",
        "cpp",
        "csharp",
        "ruby",
        "php",
        "swift",
        "scala",
        "go",
        "rust",
        "kotlin",
        "objectivec",
        "ttcn",
        "gdscript",
    }
)


class LizardCollector(Collector):
    """Cross-language cyclomatic complexity (CCN) via ``uvx lizard``."""

    name = "lizard"
    tier = 1
    required = False
    languages: frozenset[str] = _LIZARD_LANGUAGES

    def __init__(self, repo_root: Path | str | None = None) -> None:
        """Store the optional repo root; collection time uses ``ctx.repo_root``.

        Kept for parity with ``GitCollector`` — resolve does not currently need
        the repo root but the constructor signature is stable across collectors.
        """

        self._configured_repo_root: Path | None = (
            Path(repo_root) if repo_root is not None else None
        )

    # ------------------------------------------------------------------ resolve

    def resolve(self, env: ResolutionEnv) -> ResolutionResult:
        """Probe for ``uvx`` on PATH and run ``uvx lizard --version``.

        The first-run hint lands on stderr before the subprocess call: ``uvx``
        silently downloads and caches the lizard package on first use, so the
        user sees a visible progress marker instead of an apparent hang.
        """

        if shutil.which("uvx") is None:
            return Unavailable(
                reason=_UVX_NOT_FOUND_REASON,
                install_hint=_UVX_INSTALL_HINT,
            )

        print(_FIRST_RUN_HINT, file=sys.stderr)

        try:
            completed = subprocess.run(
                ["uvx", "lizard", "--version"],
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
                reason=("uvx lizard first-run cache fill timed out after 120s"),
                install_hint=_UVX_INSTALL_HINT,
            )
        except subprocess.CalledProcessError as exc:
            return Unavailable(
                reason=f"uvx lizard --version exited with status {exc.returncode}",
                install_hint=_UVX_INSTALL_HINT,
            )

        version = _parse_version_output(completed.stdout)
        return Available(version=version)

    # ------------------------------------------------------------------ collect

    def collect(self, ctx: CollectionContext) -> CollectorResult:
        """Run ``uvx lizard --xml`` over ``ctx.repo_root`` and roll up CCN."""

        try:
            completed = subprocess.run(
                ["uvx", "lizard", "--xml", ctx.repo_root],
                capture_output=True,
                text=True,
                check=True,
                timeout=_COLLECT_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            return CollectorResult(
                status="timeout",
                data={},
                issues=[
                    f"uvx lizard --xml timed out after {int(_COLLECT_TIMEOUT_SECONDS)}s."
                ],
            )
        except subprocess.CalledProcessError as exc:
            return CollectorResult(
                status="error",
                data={},
                issues=[f"uvx lizard --xml exited with status {exc.returncode}."],
            )
        except FileNotFoundError:
            return CollectorResult(
                status="error",
                data={},
                issues=["uvx not found on PATH during collect."],
            )

        return _parse_lizard_xml(completed.stdout)


# ---------------------------------------------------------------------------
# XML parsing.
# ---------------------------------------------------------------------------


def _parse_lizard_xml(xml_text: str) -> CollectorResult:
    """Parse lizard's ``cppncss`` XML into per-file rollups + aggregate.

    Returns ``status='partial'`` when at least one ``<item>`` is malformed
    (missing ``name``, unparseable CCN, or non-numeric value). Malformed
    records are skipped and described in ``issues``; well-formed siblings
    still roll up normally.
    """

    issues: list[str] = []
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError as exc:
        return CollectorResult(
            status="error",
            data={},
            issues=[f"lizard XML is not well-formed: {exc}"],
        )

    per_file_ccns: dict[str, list[int]] = {}
    all_ccns: list[int] = []

    for item in root.iter("item"):
        parsed = _parse_item(item)
        if isinstance(parsed, _ItemError):
            issues.append(parsed.message)
            continue
        file_path, ccn = parsed
        per_file_ccns.setdefault(file_path, []).append(ccn)
        all_ccns.append(ccn)

    files_block: dict[str, dict[str, Any]] = {}
    for file_path in sorted(per_file_ccns):
        ccns = per_file_ccns[file_path]
        files_block[file_path] = {
            "max_ccn": max(ccns),
            "p75_ccn": _p_nth(ccns, 75),
            "p95_ccn": _p_nth(ccns, 95),
            "function_count": len(ccns),
            "ccns": list(ccns),
        }

    aggregate = {
        "ccn_p95": _p_nth(all_ccns, 95),
        "ccn_p75": _p_nth(all_ccns, 75),
        "total_function_count": len(all_ccns),
    }

    status = "partial" if issues else "ok"
    return CollectorResult(
        status=status,
        data={"files": files_block, "aggregate": aggregate},
        issues=issues,
    )


class _ItemError:
    """Sentinel for a malformed ``<item>`` — carries the human-readable reason."""

    __slots__ = ("message",)

    def __init__(self, message: str) -> None:
        self.message = message


def _parse_item(
    item: ElementTree.Element,
) -> tuple[str, int] | _ItemError:
    """Extract ``(file_path, ccn)`` from a single ``<item>`` element.

    Lizard encodes the function name plus source location in the ``name``
    attribute: ``"funcname(args) at path/to/file.py:42"``. The third ``<value>``
    child carries the CCN. Any deviation returns an ``_ItemError`` so the
    caller can record the skip and continue.
    """

    name_attr = item.get("name")
    if name_attr is None:
        return _ItemError(
            "Skipped malformed function record: missing 'name' attribute."
        )

    location_match = _ITEM_NAME_LOCATION_RE.search(name_attr)
    if location_match is None:
        return _ItemError(
            f"Skipped malformed function record: cannot extract source "
            f"location from name={name_attr!r}."
        )
    file_path = location_match.group(1)

    value_elements = item.findall("value")
    if len(value_elements) < 3:
        return _ItemError(
            f"Skipped malformed function record: fewer than 3 <value> children "
            f"in {file_path}."
        )

    ccn_text = (value_elements[2].text or "").strip()
    try:
        ccn = int(ccn_text)
    except ValueError:
        return _ItemError(
            f"Skipped malformed function record: non-numeric CCN {ccn_text!r} "
            f"in {file_path}."
        )

    return file_path, ccn


# ---------------------------------------------------------------------------
# Version parsing.
# ---------------------------------------------------------------------------


def _parse_version_output(raw: str) -> str:
    """Strip whitespace from ``uvx lizard --version`` output.

    Lizard emits a plain version string (e.g., ``"1.22.0\\n"``). Some
    installations prefix with ``"lizard "``; the test only asserts substring
    containment, so returning the stripped raw output is robust to either.
    """

    return raw.strip()
