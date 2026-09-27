# UI Spec

This document is the UI contract.

It defines screens, states, and user workflows.

If UI behavior changes, update this file in the same pull request.

## 1. User workflows

- W1: User opens the HFVI canvas, pans or zooms the scene, selects an
  interactive object, and receives deterministic visual feedback.

## 2. Screens

### 2.1 Screen: HFVI Canvas

- Purpose: render the primary LeaferJS scene, expose deterministic interaction
  events, and keep visual evidence reproducible in CI.
- Entry conditions: `hfvi/tapes/`, `hfvi/golden/`, and Appendix K VIS are present.

## 3. UI state machines

Use Mermaid `stateDiagram-v2` for state machines.

## 4. Error handling

- Rendering failures show a blocking error state with replay tape ID and asset
  path.
- Permission errors disable write actions while preserving read-only inspection.

## 5. Analytics and events

- `hfvi_canvas_opened`
- `hfvi_object_selected`
- `hfvi_zoom_changed`
- `hfvi_replay_started`
