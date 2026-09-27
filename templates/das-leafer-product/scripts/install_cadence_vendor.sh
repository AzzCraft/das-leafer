#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENDOR_DIR="$ROOT_DIR/vendor/cadence"
LOCK_PATH="$ROOT_DIR/tooling_lock.json"
RECEIPT_NAME=".cadence-vendor-lock.json"

print_usage() {
  cat <<USAGE
Usage:
  scripts/install_cadence_vendor.sh [--from-suite PATH] [--tier oss|pro|enterprise]
      [--git-base URL] [--org ORG] [--ssh] [--force] [--unsafe-development-override]

The normal path accepts only the exact release identities in tooling_lock.json:
tag object, target commit, and publication eligibility must all match. It stages
the complete vendor tree, records the verified resolved Git tree, then atomically
swaps it into vendor/cadence. A missing requested tier is an error.

--unsafe-development-override is solely for a developer's local checkout. It is
refused in CI and release profiles, never claims publication eligibility, and
cannot be used as release evidence.
USAGE
}

TIER="oss"
FROM_SUITE=""
GIT_BASE="${DAS_SUITE_GIT_BASE:-}"
ORG=""
USE_SSH="0"
FORCE="0"
UNSAFE="0"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --tier) TIER="$2"; shift 2 ;;
    --from-suite) FROM_SUITE="$2"; shift 2 ;;
    --git-base) GIT_BASE="$2"; shift 2 ;;
    --org) ORG="$2"; shift 2 ;;
    --ssh) USE_SSH="1"; shift ;;
    --force) FORCE="1"; shift ;;
    --unsafe-development-override) UNSAFE="1"; shift ;;
    -h|--help) print_usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; print_usage; exit 2 ;;
  esac
done

case "$TIER" in oss|pro|enterprise) ;; *) echo "Invalid --tier: $TIER" >&2; exit 2 ;; esac
[[ -f "$LOCK_PATH" ]] || { echo "Missing tooling lock: $LOCK_PATH" >&2; exit 1; }

if [[ "$UNSAFE" == "1" && ( -n "${CI:-}" || -n "${DAS_RELEASE_PROFILE:-}" ) ]]; then
  echo "Unsafe Cadence vendoring is prohibited in CI and release profiles." >&2
  exit 2
fi
if [[ -e "$VENDOR_DIR" && "$FORCE" != "1" ]]; then
  echo "vendor/cadence already exists; re-run with --force only after reviewing the replacement." >&2
  exit 1
fi

repos_for_tier() {
  echo "cadence-oss"
  [[ "$TIER" == "pro" || "$TIER" == "enterprise" ]] && echo "cadence-pro"
  [[ "$TIER" == "enterprise" ]] && echo "cadence-enterprise"
}

lock_field() {
  local repo="$1" field="$2"
  python3 - "$LOCK_PATH" "$repo" "$field" <<'PY'
import json, sys
doc = json.load(open(sys.argv[1], encoding="utf-8"))
value = doc.get("cadenceVendor", {}).get("repositories", {}).get(sys.argv[2], {})
for part in sys.argv[3].split("."):
    if not isinstance(value, dict) or part not in value:
        raise SystemExit(1)
    value = value[part]
if isinstance(value, (dict, list)):
    raise SystemExit(1)
print(value)
PY
}

require_locked_identity() {
  local repo="$1"
  local target tag tag_object publication
  target="$(lock_field "$repo" targetCommit 2>/dev/null || true)"
  tag="$(lock_field "$repo" tag 2>/dev/null || true)"
  tag_object="$(lock_field "$repo" tagObject 2>/dev/null || true)"
  publication="$(lock_field "$repo" publication.status 2>/dev/null || true)"
  if [[ ! "$target" =~ ^[0-9a-f]{40}$ || -z "$tag" || ! "$tag_object" =~ ^[0-9a-f]{40}$ ]]; then
    echo "Cadence vendor lock lacks an exact tag/commit identity for requested $repo." >&2
    exit 1
  fi
  if [[ "$UNSAFE" != "1" && "$publication" != "eligible" ]]; then
    echo "Cadence vendor $repo is not publication-eligible ($publication); refusing release/default vendoring." >&2
    exit 1
  fi
}

for repo in $(repos_for_tier); do require_locked_identity "$repo"; done

url_for_repo() {
  local repo="$1"
  if [[ -n "$ORG" ]]; then
    [[ "$USE_SSH" == "1" ]] && echo "git@github.com:${ORG}/${repo}.git" || echo "https://github.com/${ORG}/${repo}.git"
    return
  fi
  if [[ -z "$GIT_BASE" ]]; then
    echo "Clone mode requires --git-base, --org, or DAS_SUITE_GIT_BASE." >&2
    exit 2
  fi
  if [[ "$USE_SSH" == "1" ]]; then
    if [[ "$GIT_BASE" =~ ^https?://github.com/([^/]+)$ ]]; then
      echo "git@github.com:${BASH_REMATCH[1]}/${repo}.git"
    else
      echo "Could not derive an SSH GitHub org from --git-base=$GIT_BASE. Pass --org explicitly." >&2
      exit 2
    fi
  else
    echo "${GIT_BASE%/}/${repo}.git"
  fi
}

STAGE_ROOT="$(mktemp -d "$ROOT_DIR/vendor/.cadence-stage.XXXXXX")"
STAGE_VENDOR="$STAGE_ROOT/cadence"
BACKUP_DIR=""
cleanup() {
  [[ -d "$STAGE_ROOT" ]] && rm -rf "$STAGE_ROOT"
  if [[ -n "$BACKUP_DIR" && -d "$BACKUP_DIR" && ! -e "$VENDOR_DIR" ]]; then mv "$BACKUP_DIR" "$VENDOR_DIR"; fi
}
trap cleanup EXIT
mkdir -p "$STAGE_VENDOR"

copy_dir() {
  local src="$1" dst="$2"
  [[ -d "$src" ]] || { echo "Required Cadence source is missing: $src" >&2; exit 1; }
  rsync -a --delete \
    --exclude '.git' --exclude '.hg' --exclude '.svn' --exclude '.cadence' \
    --exclude '__pycache__' --exclude '*.pyc' \
    --exclude '.env' --exclude '.env.*' --exclude 'secrets/' \
    --exclude '*.pem' --exclude '*.key' --exclude '*.p12' --exclude '*.pfx' --exclude 'id_rsa*' \
    "$src/" "$dst/" >/dev/null
}

verify_git_identity() {
  local repo="$1" destination="$2" expected_commit expected_tag expected_tag_object expected_tree actual_commit actual_tree actual_tag_object
  expected_commit="$(lock_field "$repo" targetCommit)"
  expected_tag="$(lock_field "$repo" tag)"
  expected_tag_object="$(lock_field "$repo" tagObject)"
  expected_tree="$(lock_field "$repo" tree)"
  actual_commit="$(git -C "$destination" rev-parse HEAD^{commit})"
  actual_tree="$(git -C "$destination" rev-parse HEAD^{tree})"
  actual_tag_object="$(git -C "$destination" rev-parse "${expected_tag}^{tag}" 2>/dev/null || true)"
  [[ "$actual_commit" == "$expected_commit" ]] || { echo "$repo target commit differs from tooling lock." >&2; exit 1; }
  [[ "$actual_tag_object" == "$expected_tag_object" ]] || { echo "$repo tag object differs from tooling lock." >&2; exit 1; }
  [[ "$actual_tree" == "$expected_tree" ]] || { echo "$repo Git tree differs from tooling lock." >&2; exit 1; }
  printf '%s' "$actual_tree"
}

install_by_clone() {
  for repo in $(repos_for_tier); do
    local destination="$STAGE_VENDOR/$repo" target tag tree content_sha256
    target="$(lock_field "$repo" targetCommit)"
    tag="$(lock_field "$repo" tag)"
    git init -q "$destination"
    git -C "$destination" remote add origin "$(url_for_repo "$repo")"
    git -C "$destination" fetch -q --no-tags origin "refs/tags/$tag:refs/tags/$tag" || { echo "Could not fetch locked $repo tag $tag" >&2; exit 1; }
    git -C "$destination" checkout -q --detach "refs/tags/$tag^{commit}" || { echo "Could not checkout locked $repo tag $tag" >&2; exit 1; }
    tree="$(verify_git_identity "$repo" "$destination")"
    rm -rf "$destination/.git"
    content_sha256="$(canonical_content_sha256 "$destination")"
    printf '%s\t%s\t%s\t%s\t%s\n' "$repo" "$tag" "$target" "$tree" "$content_sha256" >> "$STAGE_ROOT/identities.tsv"
  done
}

verify_release_identity_signature() {
  local identity="$1" repo="$2" key_id public_key key_file signature
  signature="$identity.sig"
  [[ -f "$signature" ]] || { echo "$repo release module lacks detached vendor-identity signature." >&2; exit 1; }
  key_id="$(python3 - "$identity" <<'PY'
import json, sys
signature = json.load(open(sys.argv[1], encoding="utf-8")).get("signature", {})
if (
    not isinstance(signature, dict)
    or signature.get("algorithm") != "ed25519"
    or not isinstance(signature.get("keyId"), str)
    or not signature["keyId"]
):
    raise SystemExit(1)
print(signature["keyId"])
PY
)" || { echo "$repo release/vendor-identity.json lacks a signer keyId." >&2; exit 1; }
  public_key="$(python3 - "$LOCK_PATH" "$key_id" <<'PY'
import json, sys
lock = json.load(open(sys.argv[1], encoding="utf-8"))
key = lock.get("cadenceVendor", {}).get("trustedIdentitySigners", {}).get(sys.argv[2])
if not isinstance(key, str) or not key.strip():
    raise SystemExit(1)
print(key)
PY
)" || { echo "$repo vendor signer $key_id is not trusted by tooling_lock.json." >&2; exit 1; }
  command -v openssl >/dev/null || { echo "openssl is required to verify release/vendor-identity.json." >&2; exit 1; }
  key_file="$STAGE_ROOT/$repo.vendor-identity.pub"
  printf '%s\n' "$public_key" > "$key_file"
  openssl pkeyutl -verify -pubin -inkey "$key_file" -rawin -in "$identity" -sigfile "$signature" >/dev/null 2>&1 || {
    echo "$repo release/vendor-identity signature verification failed." >&2; exit 1; }
}

canonical_content_sha256() {
  python3 - "$1" <<'PY'
import hashlib, os, pathlib, stat, sys

root = pathlib.Path(sys.argv[1]).resolve()
excluded_names = {".git", ".hg", ".svn", ".cadence", "__pycache__", "secrets"}
excluded_files = {".env", "vendor-identity.json", "vendor-identity.json.sig"}
excluded_suffixes = {".pyc", ".pem", ".key", ".p12", ".pfx"}
records = []
for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
    relative = path.relative_to(root)
    if any(part in excluded_names for part in relative.parts):
        continue
    if path.name in excluded_files or path.name.startswith(".env.") or path.name.startswith("id_rsa"):
        continue
    if path.suffix in excluded_suffixes:
        continue
    if path.is_symlink():
        raise SystemExit(f"symlink is not allowed in a vendored Cadence release: {relative}")
    if path.is_dir():
        continue
    if not path.is_file():
        raise SystemExit(f"unsupported filesystem entry in a vendored Cadence release: {relative}")
    mode = stat.S_IMODE(path.stat().st_mode)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    records.append(f"{relative.as_posix()}\\0{mode:04o}\\0{digest}\\n")
print(hashlib.sha256("".join(records).encode("utf-8")).hexdigest())
PY
}

install_from_suite() {
  local suite="$1" suite_abs release_root
  [[ -d "$suite" ]] || { echo "Could not find DAS Suite path: $suite" >&2; exit 1; }
  suite_abs="$(cd "$suite" && pwd)"; release_root="$(cd "$suite_abs/.." && pwd)"
  for repo in $(repos_for_tier); do
    local source identity
    source="$release_root/$repo"
    identity="$source/release/vendor-identity.json"
    if [[ "$UNSAFE" != "1" ]]; then
      [[ -f "$identity" ]] || { echo "$repo release module lacks release/vendor-identity.json; refusing unverified copy." >&2; exit 1; }
      python3 - "$identity" "$LOCK_PATH" "$repo" <<'PY'
import json, sys
identity, lock = json.load(open(sys.argv[1])), json.load(open(sys.argv[2]))
expected = lock["cadenceVendor"]["repositories"].get(sys.argv[3], {})
for field in ("tag", "tagObject", "targetCommit", "tree"):
    if identity.get(field) != expected.get(field):
        raise SystemExit(f"release identity mismatch: {field}")
content_sha256 = identity.get("contentSha256")
if not isinstance(content_sha256, str) or len(content_sha256) != 64 or any(ch not in "0123456789abcdef" for ch in content_sha256):
    raise SystemExit("release identity lacks a SHA-256 content digest")
if identity.get("publication", {}).get("status") != "eligible":
    raise SystemExit("release identity is not publication eligible")
PY
      verify_release_identity_signature "$identity" "$repo"
    fi
    copy_dir "$source" "$STAGE_VENDOR/$repo"
    local tree content_sha256
    tree="$(git -C "$source" rev-parse HEAD^{tree} 2>/dev/null || lock_field "$repo" tree 2>/dev/null || printf development)"
    content_sha256="$(canonical_content_sha256 "$STAGE_VENDOR/$repo")"
    if [[ "$UNSAFE" != "1" ]]; then
      [[ "$tree" == "$(lock_field "$repo" tree)" ]] || { echo "$repo source tree differs from tooling lock." >&2; exit 1; }
      [[ "$content_sha256" == "$(python3 - "$identity" <<'PY'
import json, sys
print(json.load(open(sys.argv[1], encoding="utf-8"))["contentSha256"])
PY
)" ]] || { echo "$repo source content differs from signed release identity." >&2; exit 1; }
    fi
    printf '%s\t%s\t%s\t%s\t%s\n' "$repo" "$(lock_field "$repo" tag 2>/dev/null || printf development)" "$(lock_field "$repo" targetCommit 2>/dev/null || printf development)" "$tree" "$content_sha256" >> "$STAGE_ROOT/identities.tsv"
  done
}

[[ -n "$FROM_SUITE" ]] && install_from_suite "$FROM_SUITE" || install_by_clone

python3 - "$LOCK_PATH" "$STAGE_ROOT/identities.tsv" "$STAGE_VENDOR/$RECEIPT_NAME" "$TIER" "$UNSAFE" <<'PY'
import json, pathlib, sys
lock = json.load(open(sys.argv[1], encoding="utf-8"))
identities = {}
for line in pathlib.Path(sys.argv[2]).read_text(encoding="utf-8").splitlines():
    repo, tag, commit, tree, content_sha256 = line.split("\t")
    expected = lock.get("cadenceVendor", {}).get("repositories", {}).get(repo, {})
    identities[repo] = {"tag": tag, "targetCommit": commit, "tree": tree, "contentSha256": content_sha256, "publication": expected.get("publication", {"status": "development-override"})}
doc = {
    "schemaVersion": "1.0.0",
    "mode": "development-override" if sys.argv[5] == "1" else "verified-release",
    "tier": sys.argv[4],
    "components": identities,
}
path = pathlib.Path(sys.argv[3]); path.write_text(json.dumps(doc, sort_keys=True, indent=2) + "\n", encoding="utf-8")
PY

if [[ -e "$VENDOR_DIR" ]]; then
  BACKUP_DIR="$ROOT_DIR/vendor/.cadence-rollback.$(date +%s).$$"
  mv "$VENDOR_DIR" "$BACKUP_DIR"
fi
mv "$STAGE_VENDOR" "$VENDOR_DIR"
if [[ -n "$BACKUP_DIR" ]]; then rm -rf "$BACKUP_DIR"; BACKUP_DIR=""; fi

echo "Cadence vendor installed under $VENDOR_DIR with $RECEIPT_NAME"
