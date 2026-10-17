"""JSON codecs for the adherence eval's closed types: the only place raw strings become typed values.

The types live in :mod:`praxion_evals.adherence.model`, which re-exports every
public name here, so ``model.status_to_json`` and friends stay the import path
the driver and the other modules bind to. Nothing changes on the wire.

Pure: nothing here touches a process, a file or a clock.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, assert_never, cast

from praxion_evals.adherence.infra_stop import EvidenceTail, StopRule
from praxion_evals.adherence.model import (
    Assessed,
    CheckErrored,
    CheckOutcome,
    CheckVerdict,
    Counts,
    DeclaredSettings,
    Errored,
    ErrorKind,
    Failed,
    Inferior,
    Measured,
    NonInferior,
    NoRegression,
    NotApplicable,
    NotMeasured,
    Passed,
    Regression,
    RoleVerdict,
    SessionSetup,
    SessionStatus,
    Underpowered,
    Withheld,
)
from praxion_evals.adherence.transcript import EndedOnItsOwn, RoleEnding, StoppedAtCap, Unknown

_Json = Mapping[str, Any]


def _field(data: _Json, key: str, what: str) -> Any:
    if key not in data:
        raise ValueError(f"{what} lacks {key!r}")
    return data[key]


def outcome_to_json(outcome: CheckOutcome) -> dict[str, str]:
    match outcome:
        case Passed():
            return {"outcome": "passed"}
        case Failed(detail=detail):
            return {"outcome": "failed", "detail": detail}
        case Withheld(reason=reason):
            return {"outcome": "withheld", "reason": reason}
        case NotApplicable(reason=reason):
            return {"outcome": "not applicable", "reason": reason}
        case CheckErrored(reason=reason):
            return {"outcome": "errored", "reason": reason}
        case _:
            assert_never(outcome)


def outcome_from_json(data: _Json) -> CheckOutcome:
    kind = _field(data, "outcome", "a check outcome")
    match kind:
        case "passed":
            return Passed()
        case "failed":
            return Failed(_field(data, "detail", "a failed outcome"))
        case "withheld":
            return Withheld(_field(data, "reason", "a withheld outcome"))
        case "not applicable":
            return NotApplicable(_field(data, "reason", "a not-applicable outcome"))
        case "errored":
            return CheckErrored(_field(data, "reason", "an errored outcome"))
        case _:
            raise ValueError(f"unknown check outcome {kind!r}")


def setup_to_json(setup: SessionSetup) -> dict[str, Any]:
    return {
        "arm": setup.arm,
        "checkout_commit": setup.checkout_commit,
        "role": setup.role,
        "task_id": setup.task_id,
        "template_id": setup.template_id,
        "seed": setup.seed,
    }


def setup_from_json(data: _Json) -> SessionSetup:
    return SessionSetup(
        arm=_field(data, "arm", "a session setup"),
        checkout_commit=_field(data, "checkout_commit", "a session setup"),
        role=_field(data, "role", "a session setup"),
        task_id=_field(data, "task_id", "a session setup"),
        template_id=_field(data, "template_id", "a session setup"),
        seed=int(_field(data, "seed", "a session setup")),
    )


def status_to_json(status: SessionStatus) -> dict[str, Any]:
    """A status as JSON; an echoed setup rides along under ``setup``."""
    match status:
        case Measured(
            outcomes=outcomes,
            first_request_tokens=tokens,
            role_return=role_return,
            kernel_rows=kernel_rows,
            role_ending=role_ending,
        ):
            encoded: dict[str, Any] = {
                "kind": "measured",
                "outcomes": {name: outcome_to_json(o) for name, o in outcomes.items()},
                "first_request_tokens": tokens,
            }
            if role_return is not None:
                encoded["role_return"] = role_return
            if kernel_rows:
                encoded["kernel_rows"] = [dict(row) for row in kernel_rows]
            if role_ending is not None:
                encoded["role_ending"] = role_ending_to_json(role_ending)
        case Errored(kind=kind, detail=detail, tails=tails):
            encoded = {"kind": "errored", "error_kind": kind, "detail": detail}
            if tails is not None:
                encoded["tails"] = {"error": tails.error_tail, "result": tails.result_tail}
        case NotMeasured(reason=reason):
            encoded = {"kind": "not measured", "reason": reason}
        case _:
            assert_never(status)
    if status.setup is not None:
        encoded["setup"] = setup_to_json(status.setup)
    return encoded


def status_from_json(data: _Json) -> SessionStatus:
    setup = setup_from_json(data["setup"]) if data.get("setup") else None
    kind = _field(data, "kind", "a session status")
    match kind:
        case "measured":
            outcomes = {
                name: outcome_from_json(recorded)
                for name, recorded in _field(data, "outcomes", "a measured status").items()
            }
            return Measured(
                outcomes,
                data.get("first_request_tokens"),
                setup,
                data.get("role_return"),
                tuple(data.get("kernel_rows", ())),
                role_ending_from_json(data["role_ending"]) if "role_ending" in data else None,
            )
        case "errored":
            return Errored(
                cast(ErrorKind, _field(data, "error_kind", "an errored status")),
                _field(data, "detail", "an errored status"),
                setup,
                _tails_from_json(data["tails"]) if "tails" in data else None,
            )
        case "not measured":
            return NotMeasured(_field(data, "reason", "a not-measured status"), setup)
        case _:
            raise ValueError(f"unknown session status {kind!r}")


def role_ending_to_json(ending: RoleEnding) -> dict[str, Any]:
    match ending:
        case StoppedAtCap(turns=turns, cap=cap):
            return {"kind": "stopped_at_cap", "turns": turns, "cap": cap}
        case EndedOnItsOwn(turns=turns):
            # The ending holds no cap, so the record keeps none; the wire shape allows null.
            return {"kind": "ended_on_its_own", "turns": turns, "cap": None}
        case Unknown(reason=reason):
            return {"kind": "unknown", "reason": reason}
        case _:
            assert_never(ending)


def role_ending_from_json(data: _Json) -> RoleEnding:
    what = "a role ending"
    kind = _field(data, "kind", what)
    match kind:
        case "stopped_at_cap":
            return StoppedAtCap(int(_field(data, "turns", what)), int(_field(data, "cap", what)))
        case "ended_on_its_own":
            return EndedOnItsOwn(int(_field(data, "turns", what)))
        case "unknown":
            return Unknown(_field(data, "reason", what))
        case _:
            raise ValueError(f"unknown role ending {kind!r}")


def _tails_from_json(data: _Json) -> EvidenceTail:
    return EvidenceTail(
        _field(data, "error", "an errored status's tails"),
        _field(data, "result", "an errored status's tails"),
    )


def settings_to_json(settings: DeclaredSettings) -> dict[str, Any]:
    return {
        "margin_pp": settings.margin_pp,
        "method": settings.method,
        "confidence": settings.confidence,
        "sidedness": settings.sidedness,
        "required_pairs": settings.required_pairs,
        "pair_slack": settings.pair_slack,
        "retry_policy": settings.retry_policy,
        "allowance_source": settings.allowance_source,
        "allowances": dict(settings.allowances),
        **(
            {}
            if settings.stop_rule is None
            else {"stop_rule": _stop_rule_to_json(settings.stop_rule)}
        ),
        **(
            {}
            if settings.allowance_method is None
            else {"allowance_method": settings.allowance_method}
        ),
    }


def _stop_rule_to_json(rule: StopRule) -> dict[str, Any]:
    return {
        "count": rule.count,
        "kinds": sorted(rule.kinds),
        "masking": rule.masking,
        "tail_chars": rule.tail_chars,
    }


def _stop_rule_from_json(data: _Json) -> StopRule:
    what = "the declared stop rule"
    masking = _field(data, "masking", what)
    rule = StopRule.parse(
        int(_field(data, "count", what)),
        _field(data, "kinds", what),
        int(_field(data, "tail_chars", what)),
    )
    if rule.masking != masking:
        raise ValueError(f"{what} names the masking rule {masking!r}, not {rule.masking!r}")
    return rule


def settings_from_json(data: _Json) -> DeclaredSettings:
    """Parse the declared settings; keys beyond these (``declared_at``) belong to the file."""
    what = "the declared settings"
    return DeclaredSettings(
        margin_pp=float(_field(data, "margin_pp", what)),
        method=_field(data, "method", what),
        confidence=float(_field(data, "confidence", what)),
        sidedness=_field(data, "sidedness", what),
        required_pairs=int(_field(data, "required_pairs", what)),
        pair_slack=int(_field(data, "pair_slack", what)),
        retry_policy=_field(data, "retry_policy", what),
        allowance_source=data.get("allowance_source"),
        allowances={name: int(k) for name, k in (data.get("allowances") or {}).items()},
        stop_rule=_stop_rule_from_json(data["stop_rule"]) if "stop_rule" in data else None,
        allowance_method=data.get("allowance_method"),
    )


def verdict_label(verdict: CheckVerdict) -> str:
    match verdict:
        case NoRegression():
            return "no regression"
        case Regression():
            return "regression"
        case NonInferior():
            return "non-inferior"
        case Inferior():
            return "inferior"
        case _:
            assert_never(verdict)


def _counts_to_json(counts: Counts) -> dict[str, int]:
    return {
        "both_passed": counts.both_passed,
        "lean_failed_only": counts.b,
        "lean_passed_only": counts.c,
        "both_failed": counts.both_failed,
        "n": counts.n,
    }


def _check_verdict_to_json(verdict: CheckVerdict) -> dict[str, Any]:
    detail: dict[str, Any] = {"verdict": verdict_label(verdict), **_counts_to_json(verdict.counts)}
    match verdict:
        case NoRegression(allowance=allowance) | Regression(allowance=allowance):
            detail["allowance"] = allowance
        case NonInferior(interval=interval) | Inferior(interval=interval):
            detail["interval"] = {"lower": interval.lower, "upper": interval.upper}
        case _:
            assert_never(verdict)
    return detail


def verdict_to_json(verdict: RoleVerdict) -> dict[str, Any]:
    """A role verdict as JSON; ``flip`` is absent for an underpowered role."""
    match verdict:
        case Underpowered(reason=reason, complete_pairs=complete, required_pairs=required):
            return {
                "underpowered": True,
                "reason": reason,
                "complete_pairs": complete,
                "required_pairs": required,
                "check_verdicts": {},
                "not_covered": [],
                "worst_case_lean_failures": {},
                "judged_intervals": {},
            }
        case Assessed():
            return {
                "underpowered": False,
                "flip": verdict.flip,
                "complete_pairs": verdict.complete_pairs,
                "check_verdicts": {n: verdict_label(v) for n, v in verdict.check_verdicts.items()},
                "check_details": {
                    n: _check_verdict_to_json(v) for n, v in verdict.check_verdicts.items()
                },
                "not_covered": sorted(verdict.not_covered),
                "not_covered_reasons": dict(verdict.not_covered),
                "worst_case_lean_failures": dict(verdict.worst_case_lean_failures),
                "judged_intervals": {
                    n: {"lower": v.interval.lower, "upper": v.interval.upper}
                    for n, v in verdict.check_verdicts.items()
                    if isinstance(v, NonInferior | Inferior)
                },
            }
        case _:
            assert_never(verdict)
