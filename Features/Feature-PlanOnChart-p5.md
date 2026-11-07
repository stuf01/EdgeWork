# Feature: Plan on Chart

**Source prompt:** `Prompt-5.txt`  
**Status:** Implemented

## Summary

Interactive long-only planning mode on the ticker chart: click to place entry → stop → target, drag lines to adjust, live backend-matched sizing, save plan or open in Planner. Account size and risk % are shared with the Planner via `localStorage`.

## Requirements (from prompt)

- “Plan on chart” toggle + side panel (account size, risk %)
- Click placement with 2-decimal snap; price lines (entry blue / stop red / target green)
- Draggable lines (hit-test, disable pan while dragging, resize cursor)
- Debounced `POST /api/plans/calculate` (~200ms); exceeds-account warning; R:R &lt; 2 note
- Reset, Save plan, Open in Planner
- Vitest for pure helpers (not drag logic)

## What was built

### Frontend

| Path | Role |
| --- | --- |
| `frontend/src/pages/TickerDetailPage.tsx` | Toggle, panel, debounce calculate/save, deep-link |
| `frontend/src/components/Chart.tsx` | Placement clicks, drag lines, cursor modes |
| `frontend/src/lib/planOnChart.ts` | Snap, clamp, preview math, placement review |
| `frontend/src/lib/planOnChart.test.ts` | Vitest coverage |
| `frontend/src/lib/planStorage.ts` | Shared account size / risk % persistence |

### Backend

No new endpoints. Reuses `POST /api/plans/calculate` and `POST /api/plans`.

### Tests

- Frontend Vitest: snap, ordering/clamp, client preview (floor shares), placement assessment
- Existing backend suite remains green

## UX notes

- Instruction line advances: set entry → stop → target
- Later features layered checklist evaluate + paper/setup tag onto this panel
