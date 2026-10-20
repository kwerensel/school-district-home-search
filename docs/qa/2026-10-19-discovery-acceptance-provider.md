# Anthropic compatibility preflight — October 19

The previous default `claude-sonnet-4-20250514` is retired. The existing
account's read-only model catalog includes `claude-sonnet-5-5`; both pipeline
labels and app narratives now select it by default. Explicit overrides remain
available. No SDK, provider or dependency is added.

For short one-shot text requests the documented setting is
`thinking: {type: "between_tools"}`. Deprecated non-default temperature is
omitted. Output caps and numeric guard/fallback stay in place. Mock request
regressions verify these payloads; all79 app tests, TypeScript and production
build pass. The pipeline suite passes167 tests with2 opt-in fixtures skipped.

Two bounded live requests using synthetic public facts returned HTTP400 with
a credit/billing-related category. No generation completed. No real profile,
key, raw error body or billing change is logged. Live generation therefore
remains unverified/blocked until the existing account is funded or corrected;
provider metadata availability does not imply generation credits. The app's
deterministic template remains available. No production deployment occurred.

References: [retirement](https://platform.claude.com/docs/en/about-claude/model-deprecations),
[model](https://platform.claude.com/docs/en/models/sonnet-5-5/overview),
[request migration](https://platform.claude.com/docs/en/models/sonnet-5-5/whats-new-sonnet-5-5).
Local sanitized evidence: `data/reports/anthropic_model_availability.json` and
`data/reports/anthropic_generation_preflight.json`.
