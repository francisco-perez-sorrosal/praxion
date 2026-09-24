"""Live context-layer scenario runner.

Runs the seeded scenarios as fresh, sandboxed headless ``claude -p`` sessions
over a materialized target checkout and grades what they actually did. Every
session costs money, so nothing here is reachable from ``praxion-evals``,
hooks or CI — only from its own opt-in entry point.
"""
