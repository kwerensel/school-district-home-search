# Groundtruth UI feedback pass — 2026-08-22

This directory records the UI after the August 2026 feedback pass. Images use
the live Neon-backed data and the same Hudson Valley profile as the baseline:

```text
/discover?monthlyBudget=6500&downPayment=180000&creditBand=fair&regionGroup=hudson-valley&darkSkies=3
```

Port Jervis is the selected district. The after set demonstrates the changes
that are most useful for comparison:

- `discovery-hudson-valley-desktop.png`: desktop budget and purchasing-power
  map at 1440 × 900.
- `discovery-hudson-valley-desktop-controls.png`: selected-district facts,
  explainers, and purchasing-power map at 1440 × 900.
- `discovery-hudson-valley-desktop-ranked.png`: explicit `#x of 78` ranking,
  strengths, and tradeoffs at 1440 × 900.
- `discovery-hudson-valley-compact.png`: compact purchasing-power map at
  390 × 844.
- `discovery-light-pollution-desktop.png` and
  `discovery-light-pollution-compact.png`: literal dark-to-bright district
  shading with a dynamic legend.
- `explorer-port-jervis-handoff-desktop.png`: Explorer focused on the district
  selected in Discovery, with its max-price filter preserved.
- `explorer-tree-coverage-desktop.png` and
  `explorer-tree-coverage-compact.png`: district tree-coverage shading and
  plain-language scale.
- `explorer-listing-detail-desktop.png` and
  `explorer-listing-detail-compact.png`: consumer tree-coverage category,
  clearer FEMA language, and metric explainers for a Port Jervis listing.

Environmental choropleths are explicitly labeled as district-level context.
They do not imply exact parcel, FEMA polygon, sidewalk, or address-level
precision where the current source data does not support it.
