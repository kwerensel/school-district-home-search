# PA satellite GVI promotion — October 19, 2026

User approval allows verified genuine source gaps to remain Unknown. Fresh
validation accepts only absent-road cases with exact missing ID/grain
matching, no geometric corridor intersection, nearest road beyond radius+50m,
zero corridor/observation pixels and complete computed+Unknown accounting.
Cloud, reducer, bounds and unmatched evidence remain blocking. Nothing is
imputed, and the corridor, tract threshold and three-day floor are unchanged.

- Fresh report: `data/reports/layer_gvi_ndvi_street_pa-mainline_latest.json`, promotable.
- QA visually inspected: `gvi_ndvi_street_pa-mainline.png`,
  `green_comparison_pa-mainline_staged.png`,
  `gvi_same_street_pa-mainline_staged.png`,
  `gvi_missing_buffers_pa-mainline_staged.png` under `data/reports/qa/`.
- Separate command: `gt promote --report layer_gvi_ndvi_street_pa-mainline_latest.json`.
- Public:495 tracts,248 100m buffers,251 500m buffers; all finite within[-1,1].
- Explicit 100m Unknowns:159,161,214. All three retain valid500m values.
- Derived views:61 district comparisons and499 matching listing-buffer comparisons.
- Baseline:4505 listings; no district assignment or source listing change.
- Tests:27 focused GVI,142 full pipeline/2 opt-in skipped,12 post-promote goldens;
  nine operator-context checks pass separately including live rollback fixture.
- Post-promotion read-only Discovery integration passes:9 warmed data/finance/
  ranking samples,26–89ms, with139/61/78 district counts preserved.

Verification JSON is `data/reports/qa/gvi_pa_promotion_verification.json`.
Local data artifacts remain gitignored. Hudson Valley source access remains
blocked; both-region GVI completion and post-GVI archetypes remain pending.
