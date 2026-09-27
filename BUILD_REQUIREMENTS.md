# Build requirements

The supported release verification platform is Linux x86-64.

| Tool | Version | Purpose |
| --- | --- | --- |
| Python | 3.10 or newer; CI uses 3.11 | CLI, tests, package builds |
| Bash | 4 or newer | Verification scripts |
| Git | 2.30 or newer | Project bootstrap and immutable source identities |
| Node.js | 22.23.1 | Locked frontend build and replay |
| npm | Node 22 bundled npm | Install/audit frontend lock |
| Chrome for Testing | `templates/das-leafer-product/hfvi/browser.lock.json` | Required browser replay |

Install Python tooling from `requirements-verify.txt` in a virtual environment.
Set `HFVI_BROWSER_BINARY` to the locked Chrome executable, or install it using
`scripts/ci/install_hfvi_browser.sh` with a destination outside the source tree.
Release verification fails if the required browser/toolchain is unavailable.
