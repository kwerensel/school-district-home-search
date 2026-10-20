# Preference-aware row highlights — 2026-10-19

Follow-up to `067065d`. Actual local UI screenshots, 699 × 746, existing verified
three-district shortlist, synthetic default inputs. Before screenshot saved before
code edits. No model/research calls, new data, or changes to financial math/scores.

## Changes

- Strongest values receive green cells; weakest receive amber cells, with explicit
  text labels so color is not the only cue. Applies in inline and expanded tables.
- Active priorities control meaning: lower tax and median value for local price
  reach; higher canopy for green; higher walkability/park access; lower risk,
  flood exposure and light pollution. Each row names its priority, weight /10,
  and preferred direction. Tax/median highlights are not overall affordability.
- Disabled priorities and metrics without a configured priority show neutral
  Highest/Lowest labels rather than assuming what the user prefers.
- Shared extrema are labeled tied. All-equal rows are neutral. Comparisons round
  to displayed precision; missing/nonfinite values are excluded, and fewer than
  two known values produce no extrema. Different commute anchors are not ranked.

## Captures and verification

- `before-values.jpg`: actual comparison before highlights.
- `after-active-priorities.jpg`: taxes, tree cover and walkability highlighted
  with default active priorities.
- `after-tree-priority-off.jpg`: green priority set to zero; canopy rows switch
  to neutral Highest/Lowest with no preference coloring.

Browser checked tree priority 2 -> 0 -> restored 2 and restored the expanded
comparison. 77 unit tests passed (three opt-in DB tests skipped; data path unchanged).
Typecheck, lint and production build passed; six existing shared-UI lint warnings.
Regression tests cover preference direction, unsupported/disabled context, ties,
displayed precision, missing/nonfinite values, and insufficient known values.
