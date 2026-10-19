# Signed-out Discovery/Explorer verification — 2026-10-18

Story: guided budget/priorities → optional commute caps → district comparison
and shareable shortlist → frozen Explorer listings with independent price caps.
No production deployment or full optional-account acceptance was performed.

## Evidence

- Browser loaded all 139 districts signed out, then 61 for PA Main Line.
- Wizard region/budget/priorities steps updated shareable URLs. A $6,500
  monthly budget and $18,000 gross monthly income survived canonical results
  navigation and applied the code-defined DTI ceiling.
- Public Center City test destination (39.9526, -75.1652), 45-minute cap:
  browser returned 27 eligible PA districts. Independent Node ORS verification
  returned HTTP 200 for both batches and 62/62 routable district origins.
  Origins are representative district points, explicitly distinguished from
  fixed-anchor population-weighted tract context. No live traffic is claimed.
- Comparison drawer selected Chester-Upland then Southeast Delco, displayed
  first-minus-second price/value/context differences and returned a guarded
  deterministic narrative. No unapproved archetype labels appeared.
- Lower Merion/Radnor shortlist URL carried separate caps of $843,126 and
  $845,356 for that DTI-limited test profile. Explorer showed 44/4,505 listings;
  adding 3+ bedrooms produced 16/4,505. Independent SQL returned exactly
  `(44, 16)` for those filters.
- At 390 × 844, Explorer map, shortlist polygons, filter-sheet opening/closing,
  separate price caps and 3+ bedroom filtering worked. Browser screenshots
  were visually inspected in-session. The sheet scrolls to remaining filters.
- A separate mobile journey completed `/discover` → budget → priorities →
  canonical `/discover/results` → two-district shortlist → `/explore`, retaining
  budget and both caps without signing in.
- Geocodio lookup is intentionally disabled pending a key. User approved
  free-tier-only integration and requested a reminder for October 19, 9 AM
  Eastern. Coordinate entry works without the key. No Geocodio call occurred.

## Issues found and corrected

- Fixed AccountButton SSR/client href mismatch and stale Discovery return URL.
- Results action now targets `/discover/results` with complete profile state.
- Initial commute request failed transiently, and UI correctly withheld results.
  Subsequent live adapter and browser checks succeeded; no unproven root cause
  is claimed. Safe stage/name/status diagnostics remain for recurrence.
- A rollback-only operator integration fixture held a listing-table DDL lock
  while invoking a second golden connection. It was rolled back and changed to
  run golden before the DDL transaction. No listing data changed. Explorer
  loaded after release; later fixture timing was explicitly coordinated.
- Stale browser extension connections and hot reload interruptions were resolved
  by launching Chrome and using a fresh local dev server for final mobile QA.

## Remaining gates

Satellite GVI data validation/promotion, the post-GVI archetype rebuild and
human label review remain separate gates. Full account/save/reset/delete
acceptance remains deferred. Operator roles/feature flag remain disabled.
Mapillary segmentation still lacks approved inference dependencies/model and
image-use evidence. Production deployment remains outside this goal.
