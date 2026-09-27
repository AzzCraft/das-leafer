# Project Master Doc

This document is the single source of truth for:

- requirements and scope
- repo topology and module boundaries
- cross-boundary contracts
- verification gates
- traceability from requirements to contracts and tests

If a change affects any of these elements, update this file in the same pull request.

## 2.3 Conformance profile

- DAS profile: L0 or L1 or L2

## 6.8 HFVI (High-fidelity visual interaction)

This project uses an HFVI interaction profile.

- interactionProfile: hfvi_canvas_webgl_game
- renderer: LeaferJS
- VIS spec: docs/appendices/APPENDIX_K_VIS.md
- Recommended verify gate: ./scripts/verify-hfvi

## 1. Scope

- Build and operate an HFVI product repository with deterministic visual
  interaction evidence, DAS governance docs, and executable verification gates.
- Keep canvas behavior, replay tapes, and visual baselines traceable to product
  requirements.

## 1.4 Workflows

- W1: Designer or engineer updates an HFVI interaction, records replay evidence,
  runs `./scripts/verify-hfvi`, and attaches visual diff results for review.

## 3. Repo topology

- frontend: LeaferJS render tree, interaction handlers, assets, replay tapes,
  and visual baselines.
- backend: optional service APIs consumed by the HFVI surface.
- contracts: UI event payloads, visual matrix, replay tape format, and
  compatibility fixtures.

## 4. Contracts

System-level contract inventory.

Change-level contract drafts live in:

`openspec/changes/<change-id>/contracts_plan.md`

## 0.11 Traceability

Recommended form:

Requirement -> Contract -> Verify gate

- HFVI requirement -> Appendix K VIS -> `./scripts/verify-hfvi`
- UI behavior -> `docs/ui_spec.md` -> `./scripts/verify-frontend`
- Contract change -> `contracts/` and `openspec/changes/` -> `./scripts/verify-contracts`

## 10. Verification gates

System-level verify commands.

- `./scripts/verify`
- `./scripts/verify-contracts`
- `./scripts/verify-backend`
- `./scripts/verify-frontend`
- `./scripts/verify-hfvi`

## 11. Execution plan

### 11.0 Operating model

See `docs/policies/AGENT_OPERATING_MODEL.md`.

### 11.1 Project-level WBS

- Maintain required DAS shell files and HFVI governance docs.
- Keep visual baselines, replay tapes, and interaction contracts current.
- Promote releases only after all configured verify gates pass.
