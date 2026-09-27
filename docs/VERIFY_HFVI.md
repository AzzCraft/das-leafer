# Verify HFVI

The Leafer template ships two verification layers:

- `./scripts/verify`
  - root repo/product layout, seeded artifact, and task-lock checks
  - invokes `./scripts/verify-hfvi`
- `./scripts/verify-hfvi`
  - confirms the HFVI interaction profile is declared
  - confirms the Appendix K VIS file contains the required sections
  - confirms `hfvi/tapes/` and `hfvi/golden/` exist and are not empty

For a generated Leafer product, its own `./scripts/verify-hfvi` is stricter:
it installs the exact frontend lock, builds the actual Vite/Leafer frontend,
replays the checked-in tape in the pinned Chrome-for-Testing version, compares
the resulting screenshot to the approved PNG baseline, and writes an actual
image, diff, and hash-bound receipt under `.cadence/out/hfvi/`.

The goal is a fail-closed default: removing the HFVI profile, VIS sections,
locked frontend/browser inputs, or approved visual asset roots makes the gate
fail. A project must review and explicitly record a new screenshot baseline;
the verifier never auto-updates it.
