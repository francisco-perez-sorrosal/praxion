"""Behavioral tests for the mechanical sanitizer and shipped-artifact scope filter.

Both functions run inside the `capture` subcommand *before* a defect candidate
ever reaches the git-committed `PENDING.md` (SYSTEMS_PLAN.md's "sanitize-at-
capture" divergence from `/report-upstream`) -- deterministic and judgment-
free; the command's later judgment pass is a second layer, not tested here.

These tests prove the leak-prevention contract: a planted secret,
absolute path, or username must not survive `sanitize_text`; and the scope-
filter contract: only a path shaped like a shipped Praxion artifact
family is admitted by `is_shipped_artifact_path`.
"""

from __future__ import annotations

import pytest

from scripts.praxion_feedback.sanitizer import is_shipped_artifact_path, sanitize_text


class TestSanitizeTextRedactsAbsolutePaths:
    def test_macos_home_directory_path_does_not_survive(self) -> None:
        sanitized = sanitize_text("Failed to write /Users/fperez/dev/praxion/.ai-state/foo.md")
        assert "/Users/fperez" not in sanitized

    def test_linux_home_directory_path_does_not_survive(self) -> None:
        sanitized = sanitize_text("Failed to write /home/fperez/dev/praxion/.ai-state/foo.md")
        assert "/home/fperez" not in sanitized


class TestSanitizeTextRedactsUsernames:
    def test_username_revealed_by_a_home_directory_path_does_not_survive_elsewhere_in_text(
        self,
    ) -> None:
        # The mechanical (regex, judgment-free) path is the only deterministic
        # anchor for a username; a sanitizer that redacts only the path segment
        # but leaves the same token elsewhere in the text is an incomplete leak.
        text = (
            "Failed to write /Users/fperez/dev/praxion/.ai-state/foo.md"
            " -- reported by fperez via git blame"
        )
        sanitized = sanitize_text(text)
        assert "fperez" not in sanitized


class TestSanitizeTextRedactsSecretShapedStrings:
    def test_api_key_assignment_does_not_survive(self) -> None:
        sanitized = sanitize_text("using api_key=sk_live_abcdef1234567890 to authenticate")
        assert "sk_live_abcdef1234567890" not in sanitized

    def test_bearer_token_does_not_survive(self) -> None:
        sanitized = sanitize_text(
            "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.abc123def456"
        )
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.abc123def456" not in sanitized

    def test_github_personal_access_token_does_not_survive(self) -> None:
        sanitized = sanitize_text("cloned with ghp_ABCDEFghijklmnop1234567890abcdef")
        assert "ghp_ABCDEFghijklmnop1234567890abcdef" not in sanitized

    @pytest.mark.parametrize(
        "token",
        [
            "xoxb-123456789012-1234567890123-abcdEFGHijklMNOPqrstUVWX",  # bot
            "xoxp-123456789012-1234567890123-abcdEFGHijklMNOPqrstUVWX",  # user
            "xoxo-123456789012-1234567890123-abcdEFGHijklMNOPqrstUVWX",  # oauth
            "xoxa-123456789012-1234567890123-abcdEFGHijklMNOPqrstUVWX",  # app
            "xoxs-123456789012-1234567890123-abcdEFGHijklMNOPqrstUVWX",  # session
        ],
    )
    def test_every_documented_slack_token_prefix_is_redacted(self, token: str) -> None:
        # The `xoxo-` (OAuth) case regression-guards a real leak: the char class
        # once dropped `o`, so an OAuth-shaped Slack token survived into the
        # git-committed PENDING.md.
        sanitized = sanitize_text(f"connecting with {token} to the workspace")
        assert token not in sanitized


class TestSanitizeTextPreservesSafeContent:
    def test_ordinary_error_text_without_leaks_is_unchanged(self) -> None:
        # Negative-space guard: an overly aggressive sanitizer that mangles
        # ordinary text would still pass the leak tests above.
        text = "AttributeError: 'NoneType' object has no attribute 'foo'"
        assert sanitize_text(text) == text


class TestIsShippedArtifactPathAcceptsShippedFamilies:
    @pytest.mark.parametrize(
        ("category", "path"),
        [
            ("hooks", "hooks/surface_praxion_feedback.py"),
            ("blocks", "claude/canonical-blocks/agent-pipeline.md"),
            ("agents", "agents/test-engineer.md"),
            ("scripts", "scripts/praxion_feedback/fingerprint.py"),
            ("skills", "skills/upstream-stewardship/SKILL.md"),
        ],
    )
    def test_accepts_a_path_shaped_like_its_own_category(self, category: str, path: str) -> None:
        assert is_shipped_artifact_path(path, category) is True


class TestIsShippedArtifactPathRejectsProjectLocalCode:
    def test_rejects_a_project_local_path(self) -> None:
        assert is_shipped_artifact_path("src/app.py", "scripts") is False

    def test_rejects_a_shipped_path_whose_shape_does_not_match_the_declared_category(
        self,
    ) -> None:
        # The path must match the shape of the *given* category, not merely
        # any shipped family -- a hooks-shaped path declared under "scripts"
        # is still a scope-filter rejection.
        assert is_shipped_artifact_path("hooks/surface_praxion_feedback.py", "scripts") is False
