"""
Intent: the specification layer.

A specification that is only prose drifts from the code, and everyone knows it
drifts, so after a while nobody reads it. Intent makes drift detectable rather
than asking people to prevent it:

  * Scenarios lower to executable Canon tests. A specification that cannot be
    run is not a specification here, it is a comment.

  * A goal traces to the definitions that satisfy it, and records their content
    hashes at the moment it was accepted. When a traced definition changes, the
    goal is reported as needing re-acceptance -- automatically, by hash
    comparison, rather than by someone noticing.

  * Definitions with no goal tracing to them are listed. Code nobody asked for
    is as much a finding as a goal nobody implemented.

  * Non-functional requirements are checked against the declared cost of the
    definitions they trace to, so "must complete within 250ms" is compared to
    something the compiler already knows instead of being aspirational.

The result is that the specification is the artifact a human reviews and the
agent works from, and the question "is the implementation still what we asked
for" has a mechanical answer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from canon import ast as A
from canon.canonical import short
from canon.diagnostics import Bag, Repair, Span
from canon.lexer import Lexer, T
from canon.parser import Parser


LANGUAGE_VERSION = "0.1"

METRIC_KEYS = {"millis": "wall time", "steps": "evaluation steps",
               "io": "effect operations", "tokens": "model tokens",
               "money": "spend"}

COMPARATORS = {"<=", "<", "==", ">=", ">"}


# --------------------------------------------------------------------------
# Surface declarations
# --------------------------------------------------------------------------

@dataclass
class ScenarioDecl:
    name: str = ""
    givens: list = field(default_factory=list)      # list[A.SLet]
    expectation: Optional[A.Expr] = None
    pattern: Optional[A.Pattern] = None
    subject: Optional[A.Expr] = None
    span: Span = field(default_factory=Span.unknown)


@dataclass
class MetricDecl:
    key: str = ""
    comparator: str = "<="
    value: int = 0
    span: Span = field(default_factory=Span.unknown)


@dataclass
class NonFunctionalDecl:
    name: str = ""
    metrics: list = field(default_factory=list)
    span: Span = field(default_factory=Span.unknown)


@dataclass
class GoalDecl:
    statement: str = ""
    owner: str = ""
    rationale: str = ""
    background: str = ""
    scenarios: list = field(default_factory=list)
    nonfunctional: list = field(default_factory=list)
    accepts: list = field(default_factory=list)
    rejects: list = field(default_factory=list)
    traces: list = field(default_factory=list)
    accepted_hashes: dict = field(default_factory=dict)
    span: Span = field(default_factory=Span.unknown)

    @property
    def slug(self) -> str:
        return _slug(self.statement)


# --------------------------------------------------------------------------
# Parser
# --------------------------------------------------------------------------

class IntentParser(Parser):
    def __init__(self, tokens, source="", filename="<memory>", bag=None):
        super().__init__(tokens, source, filename, bag, language="intent")
        self.goals: list = []

    def parse_decl(self):
        doc = self.skip_docs()
        if self.at_ctx("goal"):
            self.goals.append(self.parse_goal(doc))
            return None
        for fn, kw in ((self.parse_fn, "fn"), (self.parse_record, "record"),
                       (self.parse_enum, "enum"), (self.parse_alias, "alias"),
                       (self.parse_effect, "effect"), (self.parse_const, "const"),
                       (self.parse_test, "test")):
            if self.cur.is_kw(kw):
                return fn(doc)
        return None

    # ------------------------------------------------------------------

    def parse_goal(self, doc: str = "") -> GoalDecl:
        start = self.next()           # goal
        g = GoalDecl(background=doc)
        g.statement = self.parse_text_literal("the goal statement")

        while True:
            if self.at_ctx("owner"):
                self.next()
                g.owner = self.parse_text_literal("an owner")
            elif self.at_ctx("rationale"):
                self.next()
                g.rationale = self.parse_text_literal("the rationale")
            elif self.at_ctx("scenario"):
                g.scenarios.append(self.parse_scenario())
            elif self.at_ctx("nonfunctional"):
                g.nonfunctional.append(self.parse_nonfunctional())
            elif self.at_ctx("accepts"):
                self.next()
                g.accepts.append(self.parse_text_literal("an acceptance note"))
            elif self.at_ctx("rejects"):
                self.next()
                g.rejects.append(self.parse_text_literal("a rejection note"))
            elif self.at_ctx("traces"):
                self.next()
                g.traces.extend(self.parse_trace_targets(g))
            else:
                break

        if not g.scenarios:
            self.err(
                "CANON-E0102",
                f"goal {g.statement!r} has no scenarios", start,
                facts={"goal": g.statement},
                repairs=[Repair(
                    "manual", "state a checkable case",
                    'scenario "..."\n  given x = ...\n  expect f(x) is Ok',
                    start.span, 0.7)],
                notes=["A goal with no scenario cannot be checked against an "
                       "implementation, so nothing can report when it stops "
                       "being satisfied."])
        if not g.traces:
            self.bag.warn(
                "CANON-W0005",
                f"goal {g.statement!r} does not trace to any definition",
                start.span,
                facts={"goal": g.statement},
                repairs=[Repair("manual", "name what satisfies this goal",
                                "traces module.function", start.span, 0.6)],
                notes=["Without a trace this goal cannot be reported as "
                       "stale when the code behind it changes."])
        if not g.owner:
            self.bag.warn(
                "CANON-W0005",
                f"goal {g.statement!r} has no owner", start.span,
                facts={"goal": g.statement})

        g.span = self.span_from(start)
        return g

    def parse_trace_targets(self, g: GoalDecl) -> list:
        out = []
        while True:
            parts = []
            if self.cur.kind not in (T.NAME, T.UPPER):
                self.err("CANON-E0101", "expected a definition name")
                break
            parts.append(self.next().value)
            while self.cur.is_punct(".") and self.at(1).kind in (T.NAME, T.UPPER):
                self.next()
                parts.append(self.next().value)
            name = ".".join(parts)
            out.append(name)
            # An accepted hash pins the version this goal was signed off
            # against: `traces billing.refund at #abc...`
            if self.eat_ctx("at"):
                if self.cur.is_punct("#"):
                    self.next()
                    h = "#"
                    while self.cur.kind in (T.NAME, T.INT):
                        h += str(self.next().value)
                    g.accepted_hashes[name] = h
                elif self.cur.kind == T.TEXT:
                    g.accepted_hashes[name] = self.next().payload
                else:
                    self.err("CANON-E0101",
                             "expected an accepted definition hash")
            if not self.eat_punct(","):
                break
        return out

    # ------------------------------------------------------------------

    def parse_scenario(self) -> ScenarioDecl:
        start = self.next()           # scenario
        s = ScenarioDecl()
        s.name = self.parse_text_literal("a scenario name")

        while self.at_ctx("given"):
            gs = self.next()
            name = self.expect_name("a binding name")
            ty = self.parse_type() if self.eat_punct(":") else None
            self.expect_op("=", "before the value")
            stmt = A.SLet(name=name, ty=ty, value=self.parse_expr())
            stmt.span = self.span_from(gs)
            s.givens.append(stmt)

        if not self.eat_ctx("expect"):
            self.err(
                "CANON-E0101",
                f"scenario {s.name!r} has no `expect`",
                start,
                facts={"scenario": s.name},
                repairs=[Repair("insert-before", "state what should happen",
                                "expect <call> is <pattern>",
                                self.cur.span, 0.7)])
            s.expectation = A.Lit(value=False, lit_kind="bool")
            s.span = self.span_from(start)
            return s

        s.subject = self.parse_expr(no_record=True)
        if self.eat_ctx("is"):
            s.pattern = self.parse_pattern()
        else:
            s.expectation = s.subject
            s.subject = None

        s.span = self.span_from(start)
        return s

    def parse_nonfunctional(self) -> NonFunctionalDecl:
        start = self.next()           # nonfunctional
        n = NonFunctionalDecl()
        n.name = self.parse_text_literal("a requirement name")
        while self.at_ctx("metric"):
            ms = self.next()
            m = MetricDecl()
            if self.cur.kind != T.NAME:
                self.err("CANON-E0101", "expected a metric name",
                         facts={"known": sorted(METRIC_KEYS)})
                break
            m.key = self.next().value
            if m.key not in METRIC_KEYS:
                self.err("CANON-E0201", f"unknown metric {m.key!r}", ms,
                         facts={"metric": m.key,
                                "known": sorted(METRIC_KEYS)})
            if self.cur.kind == T.OP and self.cur.value in COMPARATORS:
                m.comparator = self.next().value
            else:
                self.err("CANON-E0101",
                         "expected a comparator such as <=",
                         facts={"known": sorted(COMPARATORS)})
            if self.cur.kind == T.INT:
                m.value = int(self.next().payload)
            else:
                self.err("CANON-E0101", "expected a numeric limit")
            m.span = self.span_from(ms)
            n.metrics.append(m)
        if not n.metrics:
            self.err("CANON-E0102",
                     f"non-functional requirement {n.name!r} states no metric",
                     start,
                     facts={"requirement": n.name},
                     notes=["A requirement with no metric cannot be checked "
                            "against a declared cost."])
        n.span = self.span_from(start)
        return n


# --------------------------------------------------------------------------
# Lowering
# --------------------------------------------------------------------------

class Lowering:
    """Turns scenarios into executable Canon tests."""

    def __init__(self, bag: Bag):
        self.bag = bag

    def lower_module(self, mod: A.Module, goals: list) -> A.Module:
        seen = set()
        for g in goals:
            for s in g.scenarios:
                name = f"{g.slug}: {s.name}"
                if name in seen:
                    self.bag.error(
                        "CANON-E0203",
                        f"two scenarios in the same goal are named {s.name!r}",
                        s.span, facts={"goal": g.statement, "scenario": s.name})
                seen.add(name)
                mod.decls.append(self.lower_scenario(g, s, name))
        mod.language = "intent"
        return mod

    def lower_scenario(self, g: GoalDecl, s: ScenarioDecl,
                       name: str) -> A.TestDecl:
        if s.pattern is not None:
            body_result = A.Match(
                scrutinee=s.subject,
                arms=[
                    A.MatchArm(pattern=s.pattern,
                               body=A.Lit(value=True, lit_kind="bool")),
                    A.MatchArm(pattern=A.PWild(),
                               body=A.Lit(value=False, lit_kind="bool")),
                ],
                span=s.span)
        else:
            body_result = s.expectation

        return A.TestDecl(
            name=name,
            doc=g.rationale,
            intent=g.statement,
            body=A.Block(stmts=list(s.givens), result=body_result, span=s.span),
            span=s.span)


# --------------------------------------------------------------------------
# Conformance
# --------------------------------------------------------------------------

@dataclass
class GoalStatus:
    goal: str
    owner: str = ""
    scenarios_total: int = 0
    scenarios_passed: int = 0
    failures: list = field(default_factory=list)
    traces: list = field(default_factory=list)
    missing_traces: list = field(default_factory=list)
    stale_traces: list = field(default_factory=list)
    metric_breaches: list = field(default_factory=list)

    @property
    def satisfied(self) -> bool:
        return (self.scenarios_total > 0
                and self.scenarios_passed == self.scenarios_total
                and not self.missing_traces
                and not self.stale_traces
                and not self.metric_breaches)

    def to_json(self) -> dict:
        return {"goal": self.goal, "owner": self.owner,
                "satisfied": self.satisfied,
                "scenarios": {"total": self.scenarios_total,
                              "passed": self.scenarios_passed,
                              "failures": self.failures},
                "traces": self.traces,
                "missing_traces": self.missing_traces,
                "stale_traces": self.stale_traces,
                "metric_breaches": self.metric_breaches}


@dataclass
class ConformanceReport:
    goals: list = field(default_factory=list)
    untraced_definitions: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(g.satisfied for g in self.goals)

    def to_json(self) -> dict:
        return {"ok": self.ok,
                "goals": [g.to_json() for g in self.goals],
                "untraced_definitions": self.untraced_definitions,
                "summary": {
                    "total": len(self.goals),
                    "satisfied": sum(1 for g in self.goals if g.satisfied),
                    "untraced": len(self.untraced_definitions)}}

    def render(self) -> str:
        s = self.to_json()["summary"]
        lines = [f"conformance: {s['satisfied']}/{s['total']} goals satisfied"]
        for g in self.goals:
            mark = "ok  " if g.satisfied else "FAIL"
            lines.append(f"  {mark} {g.goal}")
            lines.append(f"       scenarios {g.scenarios_passed}/"
                         f"{g.scenarios_total}"
                         + (f", traces {', '.join(g.traces)}" if g.traces else ""))
            for f in g.failures:
                lines.append(f"       failed scenario: {f}")
            for t in g.missing_traces:
                lines.append(f"       traced definition not found: {t}")
            for t in g.stale_traces:
                lines.append(f"       changed since acceptance: {t['definition']} "
                             f"({t['accepted']} -> {t['current']})")
            for m in g.metric_breaches:
                lines.append(f"       {m['requirement']}: {m['detail']}")
        if self.untraced_definitions:
            lines.append(f"  {len(self.untraced_definitions)} definitions have "
                         f"no goal: "
                         + ", ".join(self.untraced_definitions[:8])
                         + ("..." if len(self.untraced_definitions) > 8 else ""))
        return "\n".join(lines)


def conformance(goals: list, cr, hashes: Optional[dict] = None,
                test_results: Optional[list] = None,
                ignore=()) -> ConformanceReport:
    """
    Compare a specification against an implementation.

    `hashes` maps qualified name to current content hash. `test_results` is the
    output of `canon.interp.run_tests`. Everything else is derived.
    """
    hashes = hashes or {}
    results = {t["name"]: t for t in (test_results or [])}
    report = ConformanceReport()
    traced = set()

    for g in goals:
        st = GoalStatus(goal=g.statement, owner=g.owner,
                        scenarios_total=len(g.scenarios),
                        traces=list(g.traces))

        for s in g.scenarios:
            key = f"{g.slug}: {s.name}"
            r = results.get(key)
            if r is None:
                st.failures.append(f"{s.name} (not run)")
            elif r.get("passed"):
                st.scenarios_passed += 1
            else:
                detail = r.get("fault", {}).get("message") or "expectation not met"
                st.failures.append(f"{s.name}: {detail}")

        for name in g.traces:
            qn = _resolve(name, cr)
            if qn is None:
                st.missing_traces.append(name)
                continue
            traced.add(qn)
            accepted = g.accepted_hashes.get(name)
            current = hashes.get(qn, "")
            if accepted and current and not current.startswith(accepted):
                st.stale_traces.append({
                    "definition": qn,
                    "accepted": short(accepted),
                    "current": short(current)})

            fi = cr.env.fns.get(qn)
            if fi is not None:
                for nf in g.nonfunctional:
                    for m in nf.metrics:
                        breach = _check_metric(fi, m)
                        if breach:
                            st.metric_breaches.append({
                                "requirement": nf.name, "metric": m.key,
                                "detail": breach, "definition": qn})

        report.goals.append(st)

    for qn, fi in sorted(cr.env.fns.items()):
        if qn in traced or qn in ignore:
            continue
        if fi.decl is None or fi.decl.origin != "canon":
            continue
        report.untraced_definitions.append(qn)

    return report


def _check_metric(fi, m: MetricDecl) -> str:
    """Compare a stated requirement against the function's declared cost."""
    cost = fi.decl.cost
    declared = getattr(cost, m.key, None) if cost is not None else None
    if declared is None:
        return (f"{fi.qualname} declares no {m.key} budget, so "
                f"{m.key} {m.comparator} {m.value} cannot be checked")
    ok = {
        "<=": declared <= m.value, "<": declared < m.value,
        "==": declared == m.value, ">=": declared >= m.value,
        ">": declared > m.value,
    }[m.comparator]
    if not ok:
        return (f"{fi.qualname} declares {m.key} {declared}, which does not "
                f"satisfy {m.key} {m.comparator} {m.value}")
    return ""


def _resolve(name: str, cr) -> Optional[str]:
    if name in cr.env.fns:
        return name
    if name in cr.env.types or name in cr.env.consts:
        return name
    for qn in cr.env.fns:
        if qn.rsplit(".", 1)[-1] == name:
            return qn
    for qn in cr.env.consts:
        if qn.rsplit(".", 1)[-1] == name:
            return qn
    if name in cr.env.types:
        return name
    return None


def accept(goals: list, cr, hashes: dict) -> dict:
    """
    Pin every goal's traces to the definitions' current hashes.

    This is the act of signing off: from here, any change to a traced
    definition makes the goal report as stale until someone accepts it again.
    """
    out = {}
    for g in goals:
        for name in g.traces:
            qn = _resolve(name, cr)
            if qn and qn in hashes:
                g.accepted_hashes[name] = hashes[qn]
                out.setdefault(g.statement, {})[name] = hashes[qn]
    return out


def render_acceptance(goals: list) -> str:
    """Re-emit the `traces` clauses with accepted hashes, ready to paste back."""
    lines = []
    for g in goals:
        if not g.accepted_hashes:
            continue
        lines.append(f'goal "{g.statement}"')
        for name in g.traces:
            h = g.accepted_hashes.get(name)
            lines.append(f"  traces {name}" + (f" at {h}" if h else ""))
    return "\n".join(lines)


def _slug(text: str) -> str:
    out = []
    for ch in text.lower():
        if ch.isalnum():
            out.append(ch)
        elif out and out[-1] != "-":
            out.append("-")
    return "".join(out).strip("-")[:60] or "goal"


# --------------------------------------------------------------------------

def parse_intent(source: str, filename: str = "<memory>"):
    """Parse and lower Intent source. Returns (Canon Module, goals, Bag)."""
    lx = Lexer(source, filename)
    toks = lx.run()
    p = IntentParser(toks, source, filename, lx.bag)
    mod = p.parse_module()
    mod = Lowering(p.bag).lower_module(mod, p.goals)
    return mod, p.goals, p.bag
