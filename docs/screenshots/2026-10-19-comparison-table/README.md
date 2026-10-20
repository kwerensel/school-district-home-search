# Side-by-side shortlist values — 2026-10-19

Follow-up to `3992001`. All captures are actual local UI screenshots at 699 × 746,
using synthetic default budget inputs and the existing three-district shortlist.
The before capture was saved before code edits. No model calls or outside research.

## Changes

- Added a table below the shortlist with one column per selected district, in
  preference-match order. Values come directly from the existing district payload.
- Effective property-tax rates, tree cover, EPA walkability, median home values,
  canopy height, hazard risk, FEMA flood-zone share, light pollution, park access,
  transit density, drive time, AQI, modeled noise and source proxies share aligned
  rows. No repeated max-price column or new financial calculations.
- Expand comparison opens a wider dialog above the map. Sticky headers and metric
  names plus keyboard-focusable scrolling keep larger shortlists navigable.
- Missing values say Unavailable; units and interpretation stay explicit. Tax
  rates are area estimates, context is district-level, commute destinations are
  named per district, source proxies are not measured noise. Source/vintage
  metadata is available beneath both views.

## Screenshots

- `before-shortlist-cards.jpg`: prior shortlist without the values table.
- `after-expanded-comparison.jpg`: taxes, tree cover, walkability and other primary
  values side by side across Tredyffrin-Easttown, Lower Merion and Radnor Township.
- `after-additional-metrics.jpg`: scrolled table with additional context metrics.

Browser verified the expanded view, scrolling, closing, changing to two selected
columns, and restoring the original three. Observed primary values:

| Metric | Tredyffrin-Easttown | Lower Merion | Radnor Township |
|---|---:|---:|---:|
| Effective property-tax rate | 1.07% | 1.23% | 1.20% |
| Tree cover | 48.45% | 49.56% | 47.01% |
| EPA walkability / 20 | 9.94 | 11.30 | 10.76 |

Validation: 73 existing unit tests, typecheck and production build pass. Lint
passes with six pre-existing shared-UI fast-refresh warnings. The three opt-in
DB tests were skipped; the data access path and calculations were unchanged.
