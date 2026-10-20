# Hudson Valley satellite GVI promotion

The user-approved free Geofabrik recovery resolved the Overpass access blocker.
Checksum-verified October 18 New York extracts and adjacent-state boundary support
supply 111,833 full road ways. No listing expansion or new dependencies.

Both regions have fresh promotable validation reports and generated QA artifacts.
Explicit Hudson Valley promotion completed and refreshed district rollups. Public
verification preserves all 4,505 frozen listings:

| Region | Tracts | 100 m listing buffers | 500 m listing buffers | Districts |
| --- | ---: | ---: | ---: | ---: |
| PA | 495 | 248 | 251 | 61 |
| Hudson Valley | 435 | 4,042 | 4,248 | 78 |

Verified source gaps stay Unknown: PA three 100 m buffers; Hudson Valley 212
100 m and six 500 m buffers. HV has 207 absent-road cases and 11 native-grid-edge
cases with zero pixel centers/observations. Diagnostics account for every missing
ID/grain pair; unsupported geometry, insufficient clear observations and reducer
errors are still blocking unless explicitly identified as a verified source gap.
The two unsupported HV tracts remain omitted under the unchanged 99% coverage gate.
No values were imputed and no corridors or buffers were widened.

Tract, paired canopy/divergence, same-street and all 37 source-gap QA pages were
generated; representative native-edge, 500 m and final pages were visually reviewed.
PA old/new road-mask comparison is 99.9777% IoU on the shared interior 10 m grid.
Serial/four-worker satellite compositing matches exactly in multi-window tests.
Promotion uses transaction-local lock/statement timeouts supported by the Neon pooler.

Evidence (gitignored local artifacts):

- `data/reports/layer_gvi_ndvi_street_hudson-valley_latest.json`
- `data/reports/qa/gvi_both_regions_promotion_verification.json`
- `data/reports/qa/gvi_geofabrik_pa_corridor_comparison.json`
- `data/reports/qa/discovery-warm-performance.json`

Twelve post-promotion spatial goldens and the live read-only Discovery performance
check pass. Full pipeline: 177 passed, two opt-in skips. App: 79 passed, two opt-in
skips; TypeScript, lint and production build passed at the provider checkpoint.

The subsequent archetype build is blocked by model quality: corrected full-partition
silhouette 0.171887 versus required 0.25. All 139 deterministic KMeans starts at
each k=4–9 peak at 0.210875. No model was persisted, labeled or published. Existing
Anthropic credit/billing separately blocks AI generation. No production deployment.
