"""RED-first skeleton: the consumer-contract test (REQ-17).

For every `registry.CONSUMERS` entry declared at `min_mode: standard`, each
event class it needs must be recorded in `standard`
(`registry.records(event_class, Mode.STANDARD)` is True), and every field it
needs must be among that class's declared fields
(`registry.EVENTS[event_class].fields`). A registry that stops recording a
standard-min consumer's declared need -- by narrowing a class's `modes` or by
a field going undeclared -- must fail this test.

Import target does not exist yet: `hooks._observation_log.registry` (and its
sibling `modes`). This file is RED by ModuleNotFoundError until Step 3 lands
the owner package -- a GREEN result on the first run would mean this test
validates pre-existing code, not the new behavior (Register Objection).

Written from `SYSTEMS_PLAN.md`'s DS-3 and Interfaces sections, not from any
implementation -- the exact shape of `registry.EVENTS`'s value object
(`.fields`) and `registry.CONSUMERS`'s entry object (`.name`, `.min_mode`,
`.needs`) is what Step 3 must supply to make this pass.
"""

from __future__ import annotations

from hooks._observation_log import registry
from hooks._observation_log.modes import Mode


def _consumer_contract_violations(consumers, records_fn, events):
    """Pure: (consumer, event_class, reason) for every standard-min need the
    given registry state fails to honor. Takes `records_fn` and `events` as
    parameters (not read from the module directly) so both the real
    assertion and the canary below can drive it against different registry
    states without monkeypatching machinery.
    """
    violations = []
    for consumer in consumers:
        if consumer.min_mode != Mode.STANDARD:
            continue
        for event_class, fields in consumer.needs.items():
            if not records_fn(event_class, Mode.STANDARD):
                violations.append((consumer.name, event_class, "not recorded in standard"))
                continue
            missing = set(fields) - set(events[event_class].fields)
            if missing:
                violations.append((consumer.name, event_class, tuple(sorted(missing))))
    return violations


def test_every_standard_min_consumer_need_is_recorded_in_standard():
    violations = _consumer_contract_violations(
        registry.CONSUMERS, registry.records, registry.EVENTS
    )

    assert violations == []


def test_canary_dropping_a_standard_min_consumers_need_fails_the_contract():
    """Gate-liveness canary: simulate the registry narrowing one standard-min
    consumer's declared event class out of `standard` and assert the
    contract check catches it -- proving the check is not a vacuous pass.
    """
    standard_consumers = [c for c in registry.CONSUMERS if c.min_mode == Mode.STANDARD]
    assert standard_consumers, (
        "fixture assumption: at least one registered consumer is min_mode=standard"
    )
    consumer = standard_consumers[0]
    dropped_class = next(iter(consumer.needs))

    def _records_with_one_class_dropped(event_class, mode):
        if event_class == dropped_class and mode == Mode.STANDARD:
            return False
        return registry.records(event_class, mode)

    violations = _consumer_contract_violations(
        [consumer], _records_with_one_class_dropped, registry.EVENTS
    )

    assert violations != [], (
        "dropping a standard-min consumer's declared event class out of "
        "standard must be caught, not silent"
    )
