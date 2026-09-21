"""Intent: executable scenarios, hash-pinned traces, and drift detection."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "canon" / "src"))
sys.path.insert(0, str(ROOT / "intent" / "src"))

from canon import Hasher  # noqa: E402
from canon.checker import check  # noqa: E402
from canon.diagnostics import Bag  # noqa: E402
from canon.interp import run_tests  # noqa: E402
from canon.ledger import AuditLog, CapabilityBroker, Ledger  # noqa: E402
from canon.parser import parse  # noqa: E402
from intent import accept, conformance, parse_intent, render_acceptance  # noqa: E402

PROGRAM = r'''
module billing

record Money {
  amount: Int
  currency: Text
  invariant amount >= 0
}

enum ChargeStatus {
  | Pending
  | Captured
  | Refunded
}

enum RefundError {
  | NotCaptured
  | AmountExceeded(Int)
  | AlreadyRefunded
}

record Charge {
  id: Text
  amount: Money
  status: ChargeStatus
}

record Refund {
  charge_id: Text
  amount: Int
}

fn refund(c: Charge, amt: Int) -> Result<Refund, RefundError>
  intent "Refund up to the captured amount of a charge."
  requires amt > 0
  ensures true
  cost steps 5000, millis 250
{
  match c.status {
    case Pending => Err(NotCaptured)
    case Refunded => Err(AlreadyRefunded)
    case Captured =>
      if amt > c.amount.amount
        then Err(AmountExceeded(c.amount.amount))
        else Ok(Refund { charge_id: c.id, amount: amt })
  }
}

fn describe(c: Charge) -> Text
  intent "A short description of a charge."
{
  c.id
}
'''

SPEC = r'''
module billing.spec

goal "A captured charge can be refunded once, up to its captured amount"
  owner "payments-team"
  rationale "Customers must be able to reverse a charge without contacting support."

  scenario "a captured charge refunds in full"
    given c = Charge { id: "c1", amount: Money { amount: 5000, currency: "USD" }, status: Captured }
    expect refund(c, 5000) is Ok(Refund { amount: 5000 })

  scenario "a partial refund is allowed"
    given c = Charge { id: "c1", amount: Money { amount: 5000, currency: "USD" }, status: Captured }
    expect refund(c, 1200) is Ok(_)

  scenario "refunding more than the captured amount is rejected"
    given c = Charge { id: "c1", amount: Money { amount: 5000, currency: "USD" }, status: Captured }
    expect refund(c, 6000) is Err(AmountExceeded(5000))

  scenario "a pending charge cannot be refunded"
    given c = Charge { id: "c1", amount: Money { amount: 5000, currency: "USD" }, status: Pending }
    expect refund(c, 100) is Err(NotCaptured)

  nonfunctional "refunds complete promptly"
    metric millis <= 250
    metric steps <= 5000

  accepts "a refund equal to the captured amount"
  rejects "a refund against a charge that was never captured"

  traces billing.refund
'''

# A spec whose scenario does not hold against the implementation.
WRONG = SPEC.replace(
    "    expect refund(c, 6000) is Err(AmountExceeded(5000))",
    "    expect refund(c, 6000) is Ok(_)")

# A goal with no scenarios.
NO_SCENARIO = '''
module billing.spec

goal "Something we never made checkable"
  owner "payments-team"
  traces billing.refund
'''

# A requirement the declared cost does not satisfy.
TOO_SLOW = SPEC.replace("    metric millis <= 250",
                        "    metric millis <= 100")

# Traces a definition that does not exist.
BAD_TRACE = SPEC.replace("  traces billing.refund",
                         "  traces billing.refundd")


def build(program=PROGRAM, spec=SPEC):
    prog_mod, prog_bag = parse(program, "billing.canon")
    spec_mod, goals, spec_bag = parse_intent(spec, "billing.intent")
    bag = Bag()
    bag.extend(prog_bag)
    bag.extend(spec_bag)
    if bag.has_errors:
        return None, goals, bag, None
    cr = check([prog_mod, spec_mod], bag)
    hashes = {qn: di.hash
              for qn, di in Hasher().add_modules(cr.modules).items()}
    return cr, goals, cr.bag, hashes


def run_spec(cr):
    audit = AuditLog(actor="spec")
    broker = CapabilityBroker(audit=audit)
    broker.grant("spec", ["*"], reason="specification run")
    led = Ledger(broker=broker, audit=audit, actor="spec")
    return run_tests(cr, led)


def main():
    failures = []

    def case(name, fn):
        try:
            print(f"  ok    {name}: {fn()}")
        except AssertionError as ae:
            failures.append(name)
            print(f"  FAIL  {name}: {ae}")

    cr, goals, bag, hashes = build()
    if cr is None:
        print(bag.render(SPEC))
        return 1
    errs = [d for d in bag if d.severity.value == "error"]
    if errs:
        for d in errs:
            print(d.render(SPEC))
        return 1

    print("executable scenarios")

    def t_lowered():
        tests = [t for m in cr.modules for t in m.tests()]
        assert len(tests) == 4, len(tests)
        assert all(t.intent for t in tests), "a test lost its goal statement"
        return f"{len(tests)} scenarios became runnable Canon tests"
    case("scenarios lower to executable tests", t_lowered)

    def t_run():
        results = run_spec(cr)
        passed = [r for r in results if r["passed"]]
        assert len(passed) == len(results) == 4, \
            [r for r in results if not r["passed"]]
        return f"{len(passed)}/{len(results)} scenarios pass against the code"
    case("the specification runs against the implementation", t_run)

    def t_conformance():
        rep = conformance(goals, cr, hashes, run_spec(cr))
        assert rep.ok, rep.render()
        g = rep.goals[0]
        assert g.scenarios_passed == 4 and not g.missing_traces
        return f"goal satisfied: {g.scenarios_passed}/{g.scenarios_total}"
    case("a satisfied goal reports as satisfied", t_conformance)

    def t_failing_scenario():
        cr2, goals2, bag2, hashes2 = build(spec=WRONG)
        assert cr2 is not None, bag2.render(WRONG)
        rep = conformance(goals2, cr2, hashes2, run_spec(cr2))
        assert not rep.ok, "an unmet expectation reported as satisfied"
        g = rep.goals[0]
        assert g.scenarios_passed == 3, g.scenarios_passed
        assert g.failures, g.failures
        return f"{g.failures[0][:64]}"
    case("a scenario the code does not satisfy fails", t_failing_scenario)

    print("\ntraceability")

    def t_untraced():
        rep = conformance(goals, cr, hashes, run_spec(cr))
        assert "billing.describe" in rep.untraced_definitions, \
            rep.untraced_definitions
        assert "billing.refund" not in rep.untraced_definitions
        return (f"{len(rep.untraced_definitions)} definitions have no goal: "
                f"{rep.untraced_definitions}")
    case("definitions no goal traces to are listed", t_untraced)

    def t_missing_trace():
        cr2, goals2, bag2, hashes2 = build(spec=BAD_TRACE)
        assert cr2 is not None, bag2.render(BAD_TRACE)
        rep = conformance(goals2, cr2, hashes2, run_spec(cr2))
        assert not rep.ok
        assert rep.goals[0].missing_traces == ["billing.refundd"], \
            rep.goals[0].missing_traces
        return f"traced definition not found: {rep.goals[0].missing_traces}"
    case("tracing a definition that does not exist is reported",
         t_missing_trace)

    def t_accept_and_drift():
        # Sign the goal off against the current implementation.
        accepted = accept(goals, cr, hashes)
        assert accepted, "nothing was accepted"
        rep = conformance(goals, cr, hashes, run_spec(cr))
        assert rep.ok and not rep.goals[0].stale_traces, rep.render()

        # Change the traced definition. The goal must now report as stale,
        # even though every scenario still passes.
        changed = PROGRAM.replace(
            "        else Ok(Refund { charge_id: c.id, amount: amt })",
            "        else Ok(Refund { charge_id: c.id, amount: Int.max(0, amt) })")
        cr2, _, bag2, hashes2 = build(program=changed)
        assert cr2 is not None, bag2.render(changed)
        results2 = run_spec(cr2)
        assert all(r["passed"] for r in results2), \
            "the edit was supposed to preserve behaviour"

        rep2 = conformance(goals, cr2, hashes2, results2)
        stale = rep2.goals[0].stale_traces
        assert stale, "a changed traced definition did not report as stale"
        assert not rep2.ok, "a stale goal reported as satisfied"
        return (f"all scenarios still pass, but {stale[0]['definition']} "
                f"changed {stale[0]['accepted']} -> {stale[0]['current']}")
    case("a traced definition that changes after acceptance reports stale",
         t_accept_and_drift)

    def t_render_acceptance():
        accept(goals, cr, hashes)
        text = render_acceptance(goals)
        assert "traces billing.refund at #" in text, text
        return text.splitlines()[-1].strip()
    case("acceptance re-emits traces pinned to hashes", t_render_acceptance)

    print("\nnon-functional requirements")

    def t_metric_ok():
        rep = conformance(goals, cr, hashes, run_spec(cr))
        assert not rep.goals[0].metric_breaches, rep.goals[0].metric_breaches
        return "declared cost satisfies millis <= 250 and steps <= 5000"
    case("a requirement the declared cost satisfies passes", t_metric_ok)

    def t_metric_breach():
        cr2, goals2, bag2, hashes2 = build(spec=TOO_SLOW)
        assert cr2 is not None, bag2.render(TOO_SLOW)
        rep = conformance(goals2, cr2, hashes2, run_spec(cr2))
        assert not rep.ok
        b = rep.goals[0].metric_breaches
        assert b, "a breached metric was not reported"
        return b[0]["detail"]
    case("a requirement the declared cost cannot meet is reported",
         t_metric_breach)

    print("\nstructural requirements")

    def t_no_scenario():
        _, _, b, _ = build(spec=NO_SCENARIO)
        assert b.has_errors, "a goal with no scenarios compiled"
        d = next(x for x in b if "has no scenarios" in x.message)
        return d.message
    case("a goal with no scenarios does not compile", t_no_scenario)

    print("\nRESULT:", "pass" if not failures else f"FAIL ({failures})")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
