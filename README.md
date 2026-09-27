# das-leafer

`das-leafer` is a small factory tool that scaffolds a DAS-aligned product repository specialized for **HFVI** (High-fidelity Visual Interaction) projects that use **LeaferJS** as the rendering layer.

It complements `dasops`:

- `dasops` generates a general-purpose DAS product repo
- `das-leafer` generates a product repo that already includes Appendix K (VIS) artifacts and an HFVI-specific verify gate

Recommended usage:

- Use the standalone source package and materialize the exact DASOps source
  identity recorded in `release/DEPENDENCY_LOCK.json`.
- DAS Suite integration is optional; it is not required to create or verify a
  Leafer project.

`das-leafer` is now factory-first. Generic product-repo workflows such as `new-change`, `doctor`, `lock-status`, `prompt`, and task claiming delegate to `dasops` rather than carrying a forked local implementation.

Delegated commands require the declared `dasops` package in the active environment.
Leafer never falls back to an arbitrary sibling checkout.

The public v1.0 boundary supports exactly DASOps v1.0.0. Release verification
checks the locked public-source tree rather than accepting an arbitrary package
with the same command name.

## Quickstart

```bash
# Linux x86-64; Python 3.10+; Bash 4+; Git; Node.js 22.23.1 and npm.
# Keep the environment outside the source tree.
python3 -m venv ../leafer-venv
. ../leafer-venv/bin/activate
python3 -m pip install --disable-pip-version-check -r requirements-verify.txt

# Fetch and verify the exact public dependency (no internal monorepo needed).
python3 scripts/ci/materialize_dasops.py --dest ../dasops
# Install from a separate Git clone so installation does not modify the
# immutable source tree used by verification.
python3 -m pip install --no-build-isolation \
  'dasops @ git+https://github.com/AzzCraft/dasops.git@01f54872349812598190ecf0b28e0dcad2927914'
python3 -m pip install --no-build-isolation .

export HFVI_BROWSER_BINARY="$(bash scripts/ci/install_hfvi_browser.sh ../leafer-browser)"
bash ./scripts/verify --standalone

# Minimal input documents; replace their content with your product requirements.
mkdir -p ../inputs
cat > ../inputs/master_doc.md <<'EOF'
# Master Doc
## Conformance profile
interactionProfile: hfvi_canvas_webgl_game
## Repo topology
## Contracts
## Traceability
## Verification
## Execution plan
EOF
printf '# UI Spec\n' > ../inputs/ui_spec.md
cp LICENSE ../inputs/LICENSE-APACHE-2.0.txt

# Create a new HFVI product repo

dasleafer create \
  --dest ../products/my-hfvi-map \
  --master-doc ../inputs/master_doc.md \
  --ui-spec ../inputs/ui_spec.md \
  --project-id my-hfvi-map \
  --namespace com.examplecorp.maps \
  --display-name "My HFVI Map" \
  --initial-version 0.1.0 \
  --license-id Apache-2.0 \
  --license-file ../inputs/LICENSE-APACHE-2.0.txt \
  --copyright "2026 Example Corp" \
  --change-id change-0001 \
  --intent "Create HFVI LeaferJS map"
```

The identity and license arguments are required. `dasleafer` renders them into
the generated project metadata, version, frontend package, notices, and full
license file, and then pins `project_identity.json` in `tooling_lock.json`.
`UNLICENSED`, `org.example.*`, and unresolved template values are rejected.

## What you get

- `docs/appendices/APPENDIX_K_VIS.md` template
- `docs/guides/HFVI_LEAFER_MAP.md` guidance
- `scripts/verify-hfvi` HFVI profile/appendix/asset contract gate; generated
  projects add a locked-browser Vite/Leafer screenshot replay gate
- deterministic HFVI folders (`hfvi/tapes`, `hfvi/golden`)
- standard reference and lock artifacts (`STANDARD_REF.md`, `tooling_lock.json`, `local_extension_manifest.json`)

## Verification

```bash
# Standalone/release source: require the exact locked DASOps candidate tree.
bash ./scripts/verify

# DAS Tools root monorepo: validate the declared sibling workspace explicitly.
bash ./scripts/verify --workspace
```

## Repo docs

- [HFVI Profile](docs/HFVI_PROFILE.md)
- [Leafer Preset Rules](docs/LEAFER_PRESET_RULES.md)
- [Verify HFVI](docs/VERIFY_HFVI.md)

## Release status

This source is prepared for standalone review. The versioned publication gate
remains blocked until the upstream DASOps signature/exception and publication
evidence is approved. See [Release Process](docs/RELEASE_PROCESS.md).

The sample commands assume you supply existing master/UI documents and a full
license file. The generated product is verified with `bash scripts/verify`
from its directory; this builds the frontend and runs locked-browser replay.
