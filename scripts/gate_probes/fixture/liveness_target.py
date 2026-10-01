"""Code the mutation probe mutates, in a scratch copy, to see the sensor bite.

`strict_grade` is pinned at every boundary by `liveness_checks.py`, so every
mutant of it dies. `loose_label` is checked only far from its boundary, so the
mutants at its boundary survive. The probe fixes those two outcomes in advance;
a sensor that reports anything else has stopped biting.
"""


def strict_grade(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    return "C"


def loose_label(count: int) -> str:
    if count > 10:
        return "many"
    return "few"
