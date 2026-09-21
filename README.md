# Intent

The specification layer. Scenarios are executable, and goals are pinned to the
content hashes of the code that satisfies them.

Part of the [Kinode](../kinode-stack) stack. Lowers to [Canon](../canon).

## Install

```sh
pip install -e .
```

## A goal

```intent
module billing.spec

goal "A captured charge can be refunded once, up to its captured amount"
  owner "payments-team"
  rationale "Customers must be able to reverse a charge without contacting support."

  scenario "a captured charge refunds in full"
    given c = Charge { id: "c1", amount: Money { amount: 5000 }, status: Captured }
    expect refund(c, 5000) is Ok(Refund { amount: 5000 })

  scenario "refunding more than the captured amount is rejected"
    given c = Charge { id: "c1", amount: Money { amount: 5000 }, status: Captured }
    expect refund(c, 6000) is Err(AmountExceeded(5000))

  nonfunctional "refunds complete promptly"
    metric millis <= 250
    metric steps <= 5000

  accepts "a refund equal to the captured amount"
  rejects "a refund against a charge that was never captured"

  traces billing.refund at #mzod4ptezmedyw2dfsbywrumek
```

## The problem it solves

A specification that is only prose drifts from the code, everyone knows it
drifts, and after a while nobody reads it. Intent makes drift **detectable**
rather than asking people to prevent it.

**Scenarios lower to executable Canon tests.** A specification that cannot be
run is rejected — a goal with no scenarios does not compile.

```
ok  the specification runs against the implementation: 4/4 scenarios pass
```

**Traces are pinned to hashes.** `accept` records the current hash of every
traced definition. When that definition changes, the goal reports as stale —
including when every scenario still passes:

```
ok  a traced definition that changes after acceptance reports stale:
    all scenarios still pass, but billing.refund changed #mzod4pte -> #sg5x4d7p
```

That is the case a test suite cannot catch: behaviour preserved, but the code
someone signed off on is no longer the code that is running.

**Untraced code is listed.** Code nobody asked for is as much a finding as a
goal nobody implemented.

**Non-functional requirements are checked against declared cost**, so
"must complete within 250ms" is compared to something the compiler already
knows rather than being aspirational:

```
FAIL refunds complete promptly:
     billing.refund declares millis 250, which does not satisfy millis <= 100
```

## Expectation forms

| Form | Meaning |
| --- | --- |
| `expect <expr> is <pattern>` | Lowers to a match; the pattern may bind and nest |
| `expect <expr>` | The expression must evaluate to `true` |

`given name = <expr>` introduces bindings, in order, before the expectation.

## Conformance

```python
from intent import parse_intent, conformance, accept, render_acceptance
from canon.interp import run_tests

mod, goals, bag = parse_intent(text, "billing.intent")
cr = check([program_mod, mod], bag)

results = run_tests(cr, ledger)
report = conformance(goals, cr, hashes, results)
print(report.render())

accept(goals, cr, hashes)          # sign off against the current code
print(render_acceptance(goals))    # re-emit traces pinned to hashes
```

```
conformance: 4/5 goals satisfied
  ok   A captured charge can be refunded once
       scenarios 4/4, traces billing.refund
  FAIL Every decision can be explained
       scenarios 2/2
       changed since acceptance: billing.assess (#7fa2 -> #b104)
  2 definitions have no goal: billing.describe, billing.audit_note
```

## Tests

```sh
python tests/smoke_intent.py
```

## Licence

Apache-2.0. Copyright Kinode.
