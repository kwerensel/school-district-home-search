# Groundtruth UI baseline — 2026-08-21

This directory records the UI immediately before the August 2026 feedback
pass. The repository was on clean, pushed `main` at commit `5976258` before
the screenshots were added. Images were captured from the local app using its
live Neon-backed data.

## Discovery state

The captured URL used:

```text
/discover?monthlyBudget=6500&downPayment=180000&creditBand=fair&regionGroup=hudson-valley
```

The selected district was Port Jervis. The captures include:

- `discovery-hudson-valley-desktop-top.png`: budget controls, selected district,
  and desktop map at 1440 × 900.
- `discovery-hudson-valley-desktop-controls.png`: selected-district details and
  desktop map at 1440 × 900.
- `discovery-hudson-valley-desktop.png`: ranked-district list and desktop map at
  1440 × 900.
- `discovery-hudson-valley-compact-top.png`: budget controls and map at the
  390 × 844 compact breakpoint.
- `discovery-hudson-valley-compact.png`: selected-district card and map at the
  390 × 844 compact breakpoint.
- `discovery-hudson-valley.png`: the default in-app preview width at capture
  time (639 × 748).

## Explorer state

The captures include:

- `explorer-all-listings-desktop.png`: all 4,505 listings, filter panel, map,
  district polygons, and legend at 1440 × 900.
- `explorer-listing-detail-desktop.png`: the detail panel for 154 Grandview Rd,
  Ardmore, at 1440 × 900.
- `explorer-listing-detail-compact.png`: the same selected listing at the
  390 × 844 compact breakpoint.

Use the same viewport sizes and URL state for the corresponding after images.
