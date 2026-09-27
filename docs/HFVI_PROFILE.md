# HFVI Profile

`das-leafer` targets the `hfvi_canvas_webgl_game` interaction profile.

Use this profile when the product's primary behavior depends on a canvas, WebGL, or game-like interaction surface where geometry, hit areas, motion, and replayability must be specified explicitly.

The seeded Leafer template treats HFVI as a first-class contract surface:

- `docs/master_doc.md` must declare `interactionProfile: hfvi_canvas_webgl_game`
- `docs/appendices/APPENDIX_K_VIS.md` must define the visual interaction appendix
- `hfvi/tapes/` and `hfvi/golden/` must exist as deterministic asset roots
- `hfvi/browser.lock.json` pins the Chrome, viewport, locale, timezone, and
  zero-tolerance pixel-diff environment for generated projects
- the generated project's `scripts/verify-hfvi` is the profile-specific
  real-browser gate
