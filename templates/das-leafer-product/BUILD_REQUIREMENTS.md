# Build Requirements

## Toolchain

| Tool | Minimum version | Manager |
|------|----------------|---------|
| python3 | 3.11.x | system |
| node | 22.x | pinned GitHub Action / system |
| Chrome for Testing | exact version in `hfvi/browser.lock.json` | locked archive |
| git | 2.x | system |

## Build steps

```bash
python3 -m compileall .
npm ci --prefix frontend --ignore-scripts
bash ./scripts/verify
bash ./scripts/verify-hfvi
```

`verify-hfvi` is fail-closed: it requires the exact Chrome product version from
`hfvi/browser.lock.json`, builds the generated frontend from its lockfile, and
stores the actual screenshot, reviewable diff, and hash-bound receipt under
the ignored `.cadence/out/hfvi/` directory.
