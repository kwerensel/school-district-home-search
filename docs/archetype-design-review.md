# Archetype release decision — October 19, 2026

Recommendation: keep the strict clustering release gate and ship descriptive,
overlapping metric tags as the next product slice, subject to approval. The
current signed-out rankings, comparisons and commute filters already work without
archetype badges. A more expensive AI model or another API key will not resolve
numerical separation; Claude only supplies reviewed copy after model acceptance.

## What the evidence supports

All 139 eligible districts have all 16 planned model metrics after both-region GVI
promotion. Corrected HDBSCAN full-partition silhouette is 0.171887. A broader
read-only deterministic KMeans search (139 initial centers for each k=4–9) peaks
at 0.210875. Both fail the unchanged 0.25 gate; no post-GVI model is persisted.

New repeatable diagnostic: `cd pipeline && ./.venv/bin/gt archetypes audit`.
It uses a read-only database transaction, writes a non-promotable report, never
calls a label provider and cannot publish a model. Proposed theme groups retain
all inputs: green (3), access (4), environmental risk (3), noise (5), night sky (1).
Each proposed theme gets equal total weight via per-feature scaling by 1/sqrt(n).
No source metrics, production weights, cohort, k-range or gate were changed.

| Diagnostic | Current equal metric weights | Proposed equal theme weights |
| --- | ---: | ---: |
| Deterministic single-start KMeans selected k | 5 | 4 |
| Silhouette in its own weighted space | 0.196552 | 0.217167 |
| Median subsample agreement (adjusted Rand) | 0.815875 | 0.961223 |
| Minimum subsample agreement | 0.578064 | 0.654602 |

These scores use different weighted spaces and are not directly comparable proof
of improvement. This small experiment does not supersede the broader multistart
search or establish an independently validated taxonomy. Subsampling uses 24
seeded fits retaining 90% of rows with full-cohort percentiles held fixed.
Agreement measures sensitivity, not truth. Both separation scores remain below 0.25.

The five noise dimensions contribute 31.2% of current squared distance; night sky
contributes 6.3%. Strong percentile correlations include canopy/height 0.922,
walkability/transit 0.914 and satellite greenness/light pollution −0.909. These
show overlapping information, not faulty source data or proof that any one
reweighting is correct.

Local artifacts (gitignored):

- `data/reports/archetypes_design_audit_latest.json`
- `data/reports/qa/archetypes-design-audit.png`
- `data/reports/post_gvi_kmeans_multistart_audit.json`

## Proposed product change for approval

Replace the mandatory one-cluster-per-district badge with up to three independent
relative traits, computed deterministically from promoted data. A district may
have multiple traits or none. Example copy such as “More tree cover” or “Higher
transit access” describes the underlying metric, rather than claiming a natural
neighborhood type. These are illustrative labels, not assignments to districts.

Initial rules proposed for review:

- Use the existing selected comparison area's empirical percentile cohort.
- A high trait requires percentile >= 0.75; low traits require <= 0.25 where the
  metric has an explicitly documented direction. Never infer a direction for a
  general risk score or combine unrelated hazard sources into a safety label.
- Include at most one trait per theme and three total; fixed metric/copy priority
  and deterministic ties prevent duplicate canopy/height statements.
- Missing values produce no trait; fewer than three supported traits is allowed.
- Each badge names its metric and offers its value, vintage, comparison area and
  provenance. Regional/coarse data keeps its district-context qualification.
- Keep existing financial math, ranking weights, commute caps, school assignment,
  listing set and URL handoff unchanged. Tags explain data; they never assign or
  rate school quality, protected demographics or household suitability.
- No LLM is required, so this slice is independent of the Anthropic billing gate.

This changes the architecture's cluster-based badge contract and task 9.1/9.2.
AGENTS.md requires approval before a broad product/UI direction change. No tags
are wired into the main journey until that decision is made. Existing clustering
research can remain offline, with the 0.25 release gate intact.

If retaining mutually exclusive archetypes is essential, the alternative is a
separately reviewed modeling study: predefine domain weights and cohort scope,
then assess separation, resampling stability, boundary ambiguity and centroid
interpretability together. Equal-theme weighting is a candidate for that study,
not a proven unblock. Do not lower a threshold solely to accept a chosen result.

Method references: [silhouette analysis](https://scikit-learn.org/stable/auto_examples/cluster/plot_kmeans_silhouette_analysis)
and [adjusted Rand agreement](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.adjusted_rand_score.html).
