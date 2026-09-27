# Leafer Preset Rules

`das-leafer` owns the Leafer/HFVI overlay only. It does not own the generic product-repo workflow surface.

Rules for this repo and the seeded template:

- Keep standard truth external via `STANDARD_REF.md`
- Seed `tooling_lock.json` and `local_extension_manifest.json`
- Use `core-v140-baseline` in `cadence.yaml`. It is the policy-pack identity
  provided by the published Cadence OSS v1.1 source line and aligns with DAS
  Standard v1.4.0.
- Use `dasops` for generic repo mutation and task/lock workflows
- Keep Leafer-specific logic limited to the HFVI template, Appendix K guidance, and the HFVI gate
