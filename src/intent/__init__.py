"""
Intent: the specification layer.

Scenarios lower to executable Canon tests, goals trace to the definitions that
satisfy them, and those traces record content hashes at acceptance - so a
change to the code behind a goal reports the goal as stale automatically,
rather than relying on someone noticing.
"""

__version__ = "0.1.0"

from .lang import (  # noqa: E402
    COMPARATORS,
    LANGUAGE_VERSION,
    METRIC_KEYS,
    ConformanceReport,
    GoalDecl,
    GoalStatus,
    IntentParser,
    Lowering,
    MetricDecl,
    NonFunctionalDecl,
    ScenarioDecl,
    accept,
    conformance,
    parse_intent,
    render_acceptance,
)

__all__ = [
    "__version__", "LANGUAGE_VERSION",
    "parse_intent", "IntentParser", "Lowering",
    "conformance", "accept", "render_acceptance",
    "GoalDecl", "ScenarioDecl", "NonFunctionalDecl", "MetricDecl",
    "ConformanceReport", "GoalStatus",
    "METRIC_KEYS", "COMPARATORS",
]
