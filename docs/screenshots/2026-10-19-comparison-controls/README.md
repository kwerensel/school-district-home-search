# Preference editing inside comparison — 2026-10-19

Follow-up to `067b0ef`. Actual local UI captures at 699 × 746 with the existing
three-district shortlist and synthetic default inputs. Before image saved before
code edits. No model calls, external research, data writes or new finance math.

## Changes

- Added all seven 0–10 preference sliders inside the expanded comparison. Shared
  range controls give sidebar and dialog identical behavior, accessible names,
  unique IDs, keyboard support and current weight/off text.
- Edits update canonical search preferences immediately, including URL, sidebar,
  shortlist order, row highlights, and map ranks. No Apply step or separate draft.
- Weight-only changes reuse loaded verified facts and the existing pure matching
  scorer; they no longer start a district-data query or unmount the open dialog.
  Financial inputs and region changes still use their existing server data path.
- Dialog height is bounded; the table scrolls independently below controls.

## Captures

- `before-expanded-comparison.jpg`: previous highlighted table with no sliders.
- `after-controls-default.jpg`: editable preferences with original default weights.
- `after-walkability-reranked.jpg`: walkability increased from 2 to 10 inside the
  still-open dialog; Lower Merion moves from #2 to #1.
- `after-priority-off.jpg`: tree cover set to 0 inside the dialog; canopy rows
  switch from preference colors to neutral extrema.

Verified keyboard editing, immediate column reordering, highlight disabling,
closing/reopening and synchronized sidebar values. Restored walkability and tree
cover to 2 and left the expanded comparison open. 77 tests passed; three opt-in
DB tests skipped. Typecheck, lint and production build pass, with the same six
pre-existing shared-UI lint warnings.
