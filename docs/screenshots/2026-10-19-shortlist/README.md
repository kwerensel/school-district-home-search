# Direct shortlist comparisons — 2026-10-19

Follow-up to checkpoint `a1d84a2`. These actual local-browser captures use the
synthetic default budget and existing verified data. The before capture was saved
before this iteration's code edits. No model calls, external research, data writes,
or finance-assumption changes were made.

## Changes

- Selected districts are the explicit comparison population for preference match
  scores, order, strengths and compromises. Scores are recomputed from the same
  verified facts using the shared pure TypeScript scorer, not filtered regional
  scores. Priorities still control the weighted match order.
- Zero selected restores all districts in the active region. One selected district
  prompts another selection and has neutral factors without fabricated tradeoffs.
  Missing metrics stay unknown; tied factors stay neutral.
- Map colors retain the regional scale, explicitly labeled. Shortlist rankings in
  map tooltips use the shortlist denominator.
- Removed repeated max-price fields in match cards and alongside selected district
  names on the purchasing-power map. The focused district details and map hover
  still expose each calculated price. Other map layers still show selected values.

## Captures

- `before-repeated-map-prices.jpg` — actual pre-edit `a1d84a2` UI with repeated
  $750,000 labels next to each selected district. Regional ranking explanation is
  also archived in [the previous iteration](../2026-10-19-navigation/README.md).
- `after-shortlist-tradeoffs.jpg` — explicit three-district comparison explanation,
  #1-of-3 match, and compact selected names without repeated prices.
- `after-shortlist-result-cards.jpg` — differing strengths and compromises across
  the selected districts, without per-card max-price repetition.

All images are 699 × 746. Browser checks exercised three, two, one, and zero
selections, then restored the original three-district shortlist. With default
priorities: Tredyffrin-Easttown #1, Lower Merion #2, Radnor Township #3.

Validation: 73 unit tests passed, three opt-in DB tests skipped (DB path unchanged);
typecheck, lint and production build passed. Lint retains six existing shared-UI
fast-refresh warnings. New regression tests cover excluded regional outliers,
priority changes, ties, missing metrics, singleton/empty sets, and unchanged facts.
