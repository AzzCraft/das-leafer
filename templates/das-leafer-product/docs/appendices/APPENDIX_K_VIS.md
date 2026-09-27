# Appendix K (VIS): High-fidelity Visual Interaction Spec

This appendix is required when the project declares an HFVI interactionProfile.

## 1. Rendering engine

- Engine: LeaferJS
- Canvas/WebGL mode: Canvas renderer by default; WebGL may be enabled when
  locked-browser replay baselines are regenerated and approved.

## 2. Coordinate systems

- World coordinates: logical scene units with origin at the upper-left of the
  authored canvas.
- Screen coordinates: CSS pixels after viewport scale and device-pixel-ratio
  normalization.
- If mapping to geo coordinates: specify projection and transform functions

## 3. Layering rules

Define layer ordering and hit-testing rules.

Example:

1. basemap
2. roads
3. labels
4. POIs
5. overlays
6. tooltips

## 4. Zoom levels and LOD

Define zoom levels and which features appear at each LOD.

## 5. Interaction events

List events exposed by the UI layer and the event payload shapes.

- MAP_CLICK
- MAP_HOVER
- ZOOM_CHANGED
- PAN_CHANGED

## 6. Visual regression checkpoints

Define deterministic frames to capture and compare in a locked browser in CI.

- Frame IDs
- Golden baseline location
- Pixel diff threshold
- Exact browser, viewport, DPR, locale, timezone, and frontend dependency lock

## 7. Replay tapes

Define the deterministic replay tapes used by `./scripts/verify-hfvi`.

- tape format
- storage location
- how to record
- how to replay through the generated frontend in the locked browser

## 8. HFVI asset declarations

- Declare canonical Leafer/HFVI asset roots under `hfvi/`.
- Keep replay inputs in `hfvi/tapes/`.
- Keep approved browser screenshot baselines in `hfvi/golden/`.
- Pin the browser environment in `hfvi/browser.lock.json`; review a baseline
  replacement before recording it with `HFVI_ALLOW_RECORD_BASELINE=1`.

## 9. Layout conformance rules

- Treat zoom, pan, and hit-area behavior as contract surfaces rather than visual suggestions.
- Record invariant layout assumptions in this appendix before changing the render tree.
- Fail the HFVI gate when required layout assumptions or deterministic asset roots are removed.
