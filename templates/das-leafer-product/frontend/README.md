# HFVI Frontend (LeaferJS + Vite)

This is a minimal, reproducible starter for **HFVI** (High‑fidelity Visual Interaction) work using **LeaferJS**.

## Quickstart

```bash
cd frontend
npm ci
npm run dev
```

Then open the URL printed by Vite.

## Notes

- This template uses `leafer-ui` (MIT licensed) as the rendering layer.
- Keep HFVI logic in `src/` and treat `index.html` as a thin host.
- `../scripts/verify-hfvi` builds this exact lockfile, replays the checked-in
  tape through this frontend in the pinned Chrome-for-Testing browser, and
  compares an actual screenshot to the approved PNG baseline.
