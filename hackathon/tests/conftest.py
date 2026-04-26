"""Pytest configuration for hackathon/tests/.

Registers custom markers so `pytest --strict-markers` is satisfied.
"""

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "integration: marks tests that call external services (ANTHROPIC_API_KEY required). "
        "Skip with: pytest -m 'not integration'",
    )
