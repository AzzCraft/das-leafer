# Vendor folder

Use this folder for pinned third-party dependencies that are part of your build and verification.

Do not copy the DAS standard text into this vendor folder. Keep the canonical standard linkage at the repo root through `STANDARD_REF.md`, and treat that file as the only standard reference pointer for this template.

Cadence vendor policy:

`vendor/cadence/` is created only by the locked installer. It contains a
`.cadence-vendor-lock.json` receipt recording each exact tag/commit/tree and
whether it is a publication-eligible release identity. `cadencew` never falls
back to a global executable.

Normal release/default use is fail-closed until every requested Cadence entry
in `tooling_lock.json` is publication eligible:

`./scripts/install_cadence_vendor.sh --tier oss --git-base https://github.com/AzzCraft`

Release-package copy mode additionally requires each source module's signed
`release/vendor-identity.json` and its detached Ed25519 `.sig` signature to match the
lock. The signer must be in `cadenceVendor.trustedIdentitySigners`; no release
identity is trusted merely because it is adjacent to DAS Suite. It never
silently skips a requested Pro or Enterprise tier.

For local-only development, an explicit non-release override is available:

`DAS_LEAFER_ALLOW_UNSAFE_VENDOR=1 ./scripts/install_cadence_vendor.sh --from-suite <release-root>/das-suite --tier oss --unsafe-development-override`

The override is refused in CI/release profiles, marks the receipt as
`development-override`, and cannot satisfy a release gate.
