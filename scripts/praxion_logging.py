"""Canonical structured-logging configuration for the Praxion repo-root surface.

One public function, ``configure_logging``, wires `structlog` into a JSON (or
console) renderer at a chosen level. It is the repo-root counterpart to the
per-language logging baseline the `observability` skill documents — structlog is
the recommended Python default (see that skill's Service Observability Baseline).

Usage (call once, typically at a script's ``__main__``)::

    from scripts.praxion_logging import configure_logging
    configure_logging(level="INFO")          # JSON to stdout
    import structlog
    log = structlog.get_logger()
    log.info("started", component="finalize_adrs")

The module is importable via the ``pythonpath = ["."]`` convention already set in
``[tool.pytest.ini_options]``. It does not touch existing per-CLI-script
``logging.basicConfig`` calls — those remain valid for simple CLI output.

OpenTelemetry: the stdlib ``LoggerFactory`` wiring below means an OTel
``opentelemetry.sdk._logs.LoggingHandler`` can be attached to the stdlib root
logger later with zero per-call-site changes — structlog records flow through the
stdlib logging pipeline the handler observes.
"""

from __future__ import annotations

import logging

import structlog

# Guards re-entry: structlog.configure is global; calling it repeatedly is safe
# but wasteful and can surprise callers. The flag makes configure_logging a
# no-op after the first call (idempotent), unless force=True.
_CONFIGURED = False


def configure_logging(*, level: str = "INFO", json: bool = True, force: bool = False) -> None:
    """Configure structlog for the process. Idempotent after the first call.

    Args:
        level: Minimum level name (``"DEBUG"``/``"INFO"``/``"WARNING"``/...).
        json: ``True`` renders newline-delimited JSON (production/aggregation);
            ``False`` renders a human-readable console format (local dev).
        force: Re-configure even if already configured (e.g., to switch renderer).
    """
    global _CONFIGURED
    if _CONFIGURED and not force:
        return

    numeric_level = logging.getLevelName(level.upper())
    if not isinstance(numeric_level, int):
        raise ValueError(f"unknown log level: {level!r}")

    # Route stdlib logging at the chosen level so an OTel LoggingHandler attached
    # to the root logger sees the same threshold.
    logging.basicConfig(format="%(message)s", level=numeric_level)

    renderer: structlog.types.Processor = (
        structlog.processors.JSONRenderer() if json else structlog.dev.ConsoleRenderer()
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    _CONFIGURED = True
