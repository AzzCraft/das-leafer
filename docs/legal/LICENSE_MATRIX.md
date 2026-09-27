# License matrix

The das-leafer CLI and its authored scaffolding are distributed under Apache-2.0.
The full license is in `LICENSE`; attribution is in `NOTICE`.

`release/dependency_license_decisions.json` records exact Python dependency
versions and license decisions used by `scripts/release/build_release_artifacts.py`.
`THIRD_PARTY_NOTICES.md` describes the generated source/dependency inventory.
Frontend dependencies retain their own licenses and are locked in the scaffold's
`frontend/package-lock.json`. The generated product's license is supplied by its
owner through the required project identity inputs.
