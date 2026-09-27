# Release Process

1. Start with a clean standalone checkout and install the exact DASOps source
   identity from `release/DEPENDENCY_LOCK.json` into an isolated environment;
   do not use an arbitrary sibling checkout.
2. Run repository verification and the clean wheel-install smoke test.
3. Create a signed immutable `v<version>` tag through the protected release
   path. Configure the release environment with the approved SSH ED25519 SHA256 fingerprint or full OpenPGP
   fingerprint and corresponding public key.
4. Dispatch `.github/workflows/release.yml` from the default branch with that
   exact annotated tag. Validation verifies the tag signer, tag/version/commit
   identity, published DASOps identity, source verification, audits, and two
   reproducible builds of the source archive, wheel, and sdist. It generates
   exact source/dependency SBOMs, notices, checksums, manifest, and provenance.
5. A separate trusted job rechecks the protected default-branch controls,
   rebuilds the artifacts, validates the manifest/checksums, and attests the
   reviewed release manifest. It does not create a tag or GitHub Release.
6. An authorized release owner reviews the evidence, publishes the GitHub and
   Python release assets, and records the immutable release/attestation links
   in the final ledger.

Legal holder: AzzCraft Inc. (重庆艾之舟科技有限公司)

## Current publication prerequisite

The exact DASOps v1.0.0 dependency is usable for standalone verification but
its publication approval is still blocked in `release/DEPENDENCY_LOCK.json`.
A local candidate is not a published release. Do not change an existing DASOps
tag or mark the dependency eligible without independently approved signature
or historical-exception evidence, a validation run, and the GitHub Release.
The release workflow checks this before building publication evidence.

Signer keys/fingerprints are trusted repository configuration, not values taken
from a release tag. Both SSH ED25519 and OpenPGP verification are supported;
this does not designate or approve a signer automatically.

## Authenticate the DASOps exception before release validation

The pinned DASOps v1.0.0 tag is unsigned. Its publication lock remains
`blocked` until an independent release owner approves the exact historical
exception and a real DASOps GitHub Release and successful validation run exist.
A signed-status label cannot authorize this known unsigned tag. Selecting a
signed successor requires a separately reviewed source/dependency change.

Configure the following protected repository values for both release jobs:

- `DASOPS_APPROVAL_ISSUE_URL`: the exact policy issue approved by the release
  owner; its location is deliberately kept out of public source.
- `DASOPS_APPROVED_APPROVERS`: comma-separated GitHub logins of independent
  security/release approvers. The publisher account `AzzCraft` is rejected.
- `DASOPS_VALIDATION_WORKFLOW_ID`: the numeric ID of the approved DASOps
  validation workflow, checked with the exact target commit and successful run.
- `DASOPS_APPROVAL_TOKEN`: a read-only GitHub token with access to the approval
  issue. Configure it as an Actions secret; do not put it in the dependency lock.

The approver must post one unedited issue comment whose **entire body** is JSON
with the fields below. Replace values with the locked tag object and peeled
commit; the approver login must match the authenticated comment author. GitHub's
comment creation time is the authoritative approval time.

```json
{
  "schemaVersion": "das-leafer.dasops-exception.v1",
  "component": "dasops",
  "version": "1.0.0",
  "tag": "v1.0.0",
  "tagObject": "08d64edf5d70abf07d3d5be249b5016fe74544b9",
  "targetCommit": "01f54872349812598190ecf0b28e0dcad2927914",
  "exceptionId": "REPLACE-WITH-APPROVED-ID",
  "scope": "historical-unsigned-tag-only",
  "approver": "REPLACE-WITH-INDEPENDENT-GITHUB-LOGIN",
  "approvalIssue": "REPLACE-WITH-PROTECTED-APPROVAL-ISSUE-URL"
}
```

Only after verifying the independent comment and upstream release/run should
an authorized maintainer update `release/DEPENDENCY_LOCK.json` to `eligible`:
`publication.evidence.releaseIdentity` must equal the checked-in lock identity;
`githubRelease` must be the exact DASOps tag release; `validationRun` must point
to the successful run; `approval` and `signature.approval` must both point to
the same issue comment; and `signature` must set `status` to
`historical-unsigned-exception` with the approved `exceptionId`. Release
validation then checks those records live and rejects a changed remote tag.


## Compare dependency inputs across runners

The release assets include `resolved-dependencies.json`: sorted, normalized
package names, exact versions, and the SHA256 of every distribution in the
verification environment's pip report. The manifest's
`resolvedDependenciesSha256` binds that canonical file. Missing hashes fail
the build. A changed package version or distribution hash changes the release
manifest and fails the independent artifact comparison.

Runner metadata, report ordering, formatting, and download-mirror addresses do
not identify package bytes and are excluded from that canonical file. Each job
uploads its original pip report as separate Actions evidence under the
`das-leafer-dependency-report-validation-*` or
`das-leafer-dependency-report-trusted-*` name. These reports retain full download
locations and environment details but are not part of the reproducible release
asset checksums. The DASOps source dependency remains bound separately by the
source lock and its generated SPDX package entry.
