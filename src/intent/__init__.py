"""
intent, the spec layer.

scenarios lower to canon tests that run, goals trace to the definitions that
satisfy them, and those traces record content hashes when somebody accepts
them, so changing the code behind a goal reports it stale on its own instead of
waiting for somebody to notice.
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
