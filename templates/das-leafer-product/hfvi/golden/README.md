# HFVI Golden Baselines

Store reviewed golden baseline screenshots and their digest-bound provenance
records here. Each `<name>.png` must have a sibling `<name>.provenance.json`
that identifies the repository generator, source inputs, dimensions, byte size,
and SHA-256 digest. `baseline.json` remains the runtime state and pixel contract;
the provenance record governs why the binary belongs in Git.

Example:

- `zoom_level_05.png`
- `zoom_level_12.png`
