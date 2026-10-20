# Reset comparison preferences — 2026-10-19

Follow-up to `1992373`. Actual local screenshots at 699 × 746, synthetic default
inputs and the existing three-district shortlist. Before image saved before code
edits. No model, research, data or financial-calculation changes.

## Changes

- Reset preferences restores all seven weights captured when the comparison was
  opened. A copied snapshot stays stable while experimenting and reranking.
- Reset updates canonical preferences atomically; the open dialog, sidebar,
  URL, rankings and highlights share the restored state.
- Button disabled when unchanged. Closing keeps edits; reopening takes a new
  snapshot of current weights, including custom values, rather than app defaults.
- Help text makes the reset scope explicit.

## Captures

- `before-no-reset.jpg`: prior expanded comparison without reset.
- `after-experiment-reset-enabled.jpg`: changed walkability/tree priorities,
  reset enabled.
- `after-reset-restored.jpg`: original weights and shortlist order restored;
  reset disabled and dialog stays open.
- `after-custom-opening-restored.jpg`: reopened with custom walkability 3,
  experimented at 10, then reset correctly to 3.

Browser verified unchanged disabled state, multiple edits, reset, rank restoration,
and custom reopening baseline. Original walkability/tree weights restored to 2;
comparison left open. All 77 tests, typecheck, lint and production build pass;
three opt-in DB tests skipped and six existing shared-UI lint warnings remain.
