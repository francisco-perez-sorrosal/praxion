"""The checks for `liveness_target.py`; not named `test_*`, so the suite never collects them.

The mutation probe hands this file to the sensor as the target's tests. One
check pins `strict_grade` at each of its boundaries; the other leaves
`loose_label`'s boundary (10) unexamined on purpose.
"""

from liveness_target import loose_label, strict_grade


def test_strict_grade_is_pinned_at_every_boundary():
    assert strict_grade(100) == "A"
    assert strict_grade(90) == "A"
    assert strict_grade(89) == "B"
    assert strict_grade(80) == "B"
    assert strict_grade(79) == "C"
    assert strict_grade(0) == "C"


def test_loose_label_is_checked_only_away_from_its_boundary():
    assert loose_label(100) == "many"
    assert loose_label(0) == "few"
