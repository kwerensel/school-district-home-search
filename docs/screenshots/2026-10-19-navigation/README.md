# Discovery and Explorer iteration — 2026-10-19

All captures use the existing promoted data and synthetic default budget inputs;
model access and outside research were disabled. These are local UI QA captures,
not a production deployment.

## Committed baseline

The baseline captures were rendered from commit `65db6de` in an isolated temporary
source snapshot after the changes were underway. They faithfully reproduce the
previous committed UI; they are not presented as captures made before editing.

- `baseline-65db6de-discovery-goal-checklist.jpg` — 1280 × 720; the fixed goals
  checklist and district-only comparison controls.
- `baseline-65db6de-explorer-mobile-filters.jpg` — 699 × 746; reproduces Leaflet
  layers covering the mobile filter sheet and the missing narrow-screen Discover
  link.

## In-progress captures before the multi-select pass

These were taken immediately when the user requested screenshots, after the
initial conversation/navigation correction had begun and before adding district
multi-select and the new ranking labels.

- `before-discovery-conversation.jpg` — 699 × 746.
- `before-discovery-multi-select.jpg` — 699 × 746.

## Updated UI

- `after-open-ended-conversation.jpg` — 1280 × 720; conversation first, unrestricted
  optional context, place lookup, and optional district tools.
- `after-three-district-purchasing-power.jpg` — 699 × 746; Lower Merion, Radnor
  Township and Tredyffrin-Easttown selected together; purchasing-power layer kept
  independent from selection.
- `after-preference-match-ranking.jpg` — 699 × 746; preference-match ordering,
  explicit regional peer scope, and selected-district map.
- `after-explorer-mobile-filters.jpg` — 699 × 746; filter sheet above the map,
  visible Discover navigation, and 134 frozen listings in the three-district
  shortlist.

The same three map districts remained selected when switching to tree coverage
and back to purchasing power. Returning from Explorer preserved the budget,
region, and shortlist. No geospatial assignments or promoted values were changed.
