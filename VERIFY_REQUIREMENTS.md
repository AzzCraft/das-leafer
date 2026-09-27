# Verify Requirements — das-leafer

```bash
# Standalone/release verification requires the exact locked DASOps tree.
./scripts/verify

# Root-monorepo development verification uses the declared sibling component.
./scripts/verify --workspace
```

## Prerequisites

- `python3` on PATH (3.10+)
- `bash` on PATH
- the exact DASOps v1.0.0 public-source tree named by
  `release/DEPENDENCY_LOCK.json` as sibling `../dasops`

## What verify checks

1. Unit tests pass.
2. HFVI lock-status smoke.
3. Preset/overlay delegation to dasops.
4. Exact DASOps source-tree identity and a clean wheel-install smoke test.
