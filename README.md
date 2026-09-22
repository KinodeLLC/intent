# Intent

the spec layer. scenarios are runnable tests, and a goal is pinned to the hash
of the code that satisfies it.

part of [kinode](../kinode-stack). lowers to [canon](../canon).

## install

```sh
pip install -e .
```

## example

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

## drift

a spec that is only prose drifts away from the code, everybody knows it drifts,
and after a while nobody opens it. this makes the drift something you find out
about instead of something people are supposed to prevent

scenarios lower to canon tests and they run, so a spec you cannot run is not a
spec, and a goal with no scenarios on it will not compile

```
ok  the specification runs against the implementation: 4/4 scenarios pass
```

`accept` writes down the current hash of every definition a goal traces to. when
one of those definitions changes the goal comes back stale, including when every
scenario still passes, which is the case tests cannot catch because behaviour did
not change, only the code somebody signed off on

```
ok  a traced definition that changes after acceptance reports stale:
    all scenarios still pass, but billing.refund changed #mzod4pte -> #sg5x4d7p
```

definitions with no goal tracing to them get listed too

non functional requirements get checked against the cost the function declared,
so `millis <= 250` is compared to something the compiler already knows rather
than sitting there as a wish

```
FAIL refunds complete promptly:
     billing.refund declares millis 250, which does not satisfy millis <= 100
```

## expectations

| form | what it does |
| --- | --- |
| `expect <expr> is <pattern>` | lowers to a match, the pattern can bind and nest |
| `expect <expr>` | has to come out `true` |

`given name = <expr>` puts bindings in place, in order, before the expectation

## conformance

```python
from intent import parse_intent, conformance, accept, render_acceptance
from canon.interp import run_tests

mod, goals, bag = parse_intent(text, "billing.intent")
cr = check([program_mod, mod], bag)

results = run_tests(cr, ledger)
report = conformance(goals, cr, hashes, results)
print(report.render())

accept(goals, cr, hashes)          # sign off against what is there now
print(render_acceptance(goals))    # traces with the hashes on them, paste back
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

## tests

```sh
python tests/smoke_intent.py
```

## licence

Apache-2.0, Kinode.
