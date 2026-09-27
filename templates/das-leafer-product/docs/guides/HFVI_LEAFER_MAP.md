# HFVI + LeaferJS Map Guide

This guide explains how to use LeaferJS as the rendering layer while keeping your project governed by the DAS Standard.

## 1. When to use HFVI

Use HFVI when the primary UI is not DOM-first and your core behavior depends on Canvas/WebGL performance.

A map UI with large datasets and fast zoom in/out is a classic HFVI scenario.

## 2. Required Master Doc declarations

In `docs/master_doc.md`:

- Declare `interactionProfile: hfvi_canvas_webgl_game`.
- Name the rendering engine: LeaferJS.
- Link Appendix K: `docs/appendices/APPENDIX_K_VIS.md`.

## 3. Contracts-first data flow

Do not let rendering code call your backend directly.

Instead:

- Define tile/region data contracts in `contracts/`.
- Define UI event contracts for interactions.
- Keep all cross-boundary changes compatible (additive preferred).

## 4. Replay and visual regression

A reliable verification gate for HFVI combines:

- Deterministic replay tapes
- Visual regression screenshots

The default template makes `./scripts/verify-hfvi` an executable baseline:
it replays the checked-in tape through the built Leafer frontend in the locked
browser and compares the resulting screenshot to the reviewed PNG baseline.

## 5. Recommended module boundaries

- `ui/map-engine` (LeaferJS wrapper): draw-only, no business logic.
- `features/visualization`: data fetch + transform + LOD.
- `features/interaction`: translate engine events into business actions.

## 6. Next steps

- Fill in `docs/appendices/APPENDIX_K_VIS.md`.
- Extend `./scripts/verify-hfvi` only with reviewed tapes, locked browser/tool
  inputs, and approved screenshot baselines; do not replace it with a model or
  a self-updating visual test.
- Add a small set of golden replay tapes for CI.
