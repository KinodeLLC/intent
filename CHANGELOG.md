# Changelog

Keep a Changelog format, SemVer. Pre-1.0: breaking changes bump the minor.

## [Unreleased]

## [0.1.0] - 2026-09-21

### Added
- Goals with owners, rationale, acceptance and rejection notes.
- Scenarios that lower to executable Canon tests. A goal with no scenarios does
  not compile.
- Traces pinned to definition content hashes, so a change to traced code
  reports the goal as stale even when every scenario still passes.
- Non-functional requirements checked against declared cost.
- Conformance reporting, including definitions no goal traces to.
