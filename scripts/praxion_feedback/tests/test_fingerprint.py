"""Behavioral tests for the fingerprint/dedup contract.

`compute_fingerprint` is `sha256(category + normalized_artifact_path +
normalized_error)` -- SYSTEMS_PLAN.md § Interfaces names this normalization
"the dedup contract" and Risk Assessment calls it "the primary test target":
under-normalization admits duplicate candidates for the same recurring
defect, over-normalization collapses genuinely distinct defects into one
fingerprint. Both failure directions are tested explicitly below.

Two layers: direct `normalize_error` tests pinpoint exactly which noise
category breaks normalization; `compute_fingerprint` tests prove the
end-to-end same-defect/different-defect dedup contract this module owns.
"""

from __future__ import annotations

from scripts.praxion_feedback.fingerprint import compute_fingerprint, normalize_error


class TestNormalizeErrorStripsVolatileNoise:
    """Run-specific noise must collapse so the *same* recurring defect matches."""

    def test_leading_and_trailing_whitespace_is_stripped(self) -> None:
        assert normalize_error("  boom  ") == normalize_error("boom")

    def test_line_number_is_stripped(self) -> None:
        first = normalize_error('File "scripts/foo.py", line 42, in bar')
        second = normalize_error('File "scripts/foo.py", line 87, in bar')
        assert first == second

    def test_memory_address_is_stripped(self) -> None:
        first = normalize_error("<Foo object at 0x7f8a3c001230>")
        second = normalize_error("<Foo object at 0x55d2916e8b10>")
        assert first == second

    def test_iso_timestamp_is_stripped(self) -> None:
        first = normalize_error("capture failed at 2026-07-23T10:15:30Z")
        second = normalize_error("capture failed at 2026-11-02T03:44:12Z")
        assert first == second

    def test_pid_is_stripped(self) -> None:
        first = normalize_error("worker pid 12345 crashed")
        second = normalize_error("worker pid 98765 crashed")
        assert first == second

    def test_temp_dir_token_is_stripped(self) -> None:
        first = normalize_error("could not read /tmp/tmpAbCdEf12/payload.json")
        second = normalize_error("could not read /tmp/tmpZzYyXx99/payload.json")
        assert first == second

    def test_uuid_token_is_stripped(self) -> None:
        first = normalize_error("session 550e8400-e29b-41d4-a716-446655440000 failed")
        second = normalize_error("session 6ba7b810-9dad-11d1-80b4-00c04fd430c8 failed")
        assert first == second

    def test_absolute_path_prefix_is_stripped(self) -> None:
        first = normalize_error('File "/Users/fperez/dev/praxion/scripts/foo.py"')
        second = normalize_error('File "/home/ci-runner/work/praxion/scripts/foo.py"')
        assert first == second

    def test_absolute_path_normalizes_to_the_same_shape_as_a_repo_relative_path(self) -> None:
        absolute = normalize_error('File "/Users/fperez/dev/praxion/scripts/foo.py", line 12')
        relative = normalize_error('File "scripts/foo.py", line 12')
        assert absolute == relative

    def test_differing_semantic_message_is_not_collapsed(self) -> None:
        # Negative-space guard: a normalizer aggressive enough to strip every
        # difference above must still distinguish genuinely different errors.
        attribute_error = normalize_error(
            "AttributeError: 'NoneType' object has no attribute 'foo'"
        )
        key_error = normalize_error("KeyError: 'bar'")
        assert attribute_error != key_error


class TestComputeFingerprintStability:
    """Same logical defect -> identical fingerprint, across realistic capture noise."""

    def test_identical_inputs_produce_identical_fingerprint(self) -> None:
        first = compute_fingerprint("scripts", "scripts/foo.py", "boom")
        second = compute_fingerprint("scripts", "scripts/foo.py", "boom")
        assert first == second

    def test_whitespace_only_difference_in_error_yields_same_fingerprint(self) -> None:
        first = compute_fingerprint("scripts", "scripts/foo.py", "  boom  ")
        second = compute_fingerprint("scripts", "scripts/foo.py", "boom")
        assert first == second

    def test_absolute_vs_repo_relative_path_in_error_text_yields_same_fingerprint(self) -> None:
        first = compute_fingerprint(
            "scripts",
            "scripts/foo.py",
            "Traceback (most recent call last):\n"
            '  File "/Users/fperez/dev/praxion/scripts/foo.py", line 42, in bar\n'
            "AttributeError: boom",
        )
        second = compute_fingerprint(
            "scripts",
            "scripts/foo.py",
            "Traceback (most recent call last):\n"
            '  File "scripts/foo.py", line 87, in bar\n'
            "AttributeError: boom",
        )
        assert first == second

    def test_realistic_multiline_traceback_with_mixed_noise_normalizes_to_same_fingerprint(
        self,
    ) -> None:
        # Two "captures" of the same recurring bug, shaped like real tracebacks,
        # differing only in every noise category normalization must strip at once.
        capture_one = compute_fingerprint(
            "hooks",
            "hooks/surface_praxion_feedback.py",
            "Traceback (most recent call last):\n"
            '  File "/Users/fperez/dev/praxion/hooks/surface_praxion_feedback.py", '
            "line 12, in main\n"
            "    candidates = read(pending_path)\n"
            '  File "/Users/fperez/dev/praxion/scripts/praxion_feedback/'
            'candidate_store.py", line 30, in read\n'
            "    raise RuntimeError(f'pid 12345 could not open "
            "/tmp/tmpAbCdEf12/session-550e8400-e29b-41d4-a716-446655440000 "
            "at 2026-07-23T10:15:30Z')\n"
            "RuntimeError: <PendingStore object at 0x7f8a3c001230> not found",
        )
        capture_two = compute_fingerprint(
            "hooks",
            "hooks/surface_praxion_feedback.py",
            "Traceback (most recent call last):\n"
            '  File "hooks/surface_praxion_feedback.py", line 19, in main\n'
            "    candidates = read(pending_path)\n"
            '  File "scripts/praxion_feedback/candidate_store.py", line 41, in read\n'
            "    raise RuntimeError(f'pid 98765 could not open "
            "/tmp/tmpZzYyXx99/session-6ba7b810-9dad-11d1-80b4-00c04fd430c8 "
            "at 2026-11-02T03:44:12Z')\n"
            "RuntimeError: <PendingStore object at 0x55d2916e8b10> not found",
        )
        assert capture_one == capture_two

    def test_repeated_calls_on_the_same_capture_are_deterministic(self) -> None:
        capture = (
            "Traceback (most recent call last):\n"
            '  File "/Users/fperez/dev/praxion/hooks/surface_praxion_feedback.py", '
            "line 12, in main\n"
            "RuntimeError: pid 12345 at 0x7f8a3c001230 2026-07-23T10:15:30Z /tmp/tmpAbCdEf12"
        )
        first = compute_fingerprint("hooks", "hooks/surface_praxion_feedback.py", capture)
        second = compute_fingerprint("hooks", "hooks/surface_praxion_feedback.py", capture)
        assert first == second


class TestComputeFingerprintCollisionAvoidance:
    """Different logical defects must never collapse into the same fingerprint."""

    def test_differing_category_yields_different_fingerprint(self) -> None:
        hooks_fp = compute_fingerprint("hooks", "hooks/foo.py", "boom")
        scripts_fp = compute_fingerprint("scripts", "hooks/foo.py", "boom")
        assert hooks_fp != scripts_fp

    def test_differing_artifact_path_yields_different_fingerprint(self) -> None:
        foo_fp = compute_fingerprint("scripts", "scripts/foo.py", "boom")
        bar_fp = compute_fingerprint("scripts", "scripts/bar.py", "boom")
        assert foo_fp != bar_fp

    def test_differing_semantic_error_yields_different_fingerprint(self) -> None:
        attribute_error_fp = compute_fingerprint(
            "scripts", "scripts/foo.py", "AttributeError: 'NoneType' object has no attribute 'foo'"
        )
        key_error_fp = compute_fingerprint("scripts", "scripts/foo.py", "KeyError: 'bar'")
        assert attribute_error_fp != key_error_fp


class TestComputeFingerprintShape:
    def test_returns_a_64_character_hex_sha256_digest(self) -> None:
        fingerprint = compute_fingerprint("scripts", "scripts/foo.py", "boom")
        assert len(fingerprint) == 64
        assert all(char in "0123456789abcdef" for char in fingerprint)
