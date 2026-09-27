"""Validated, rendered identity for a generated DAS Leafer product repository."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path


PROJECT_ID_RE = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*\Z")
NAMESPACE_RE = re.compile(r"[a-z][a-z0-9-]*(?:\.[a-z][a-z0-9-]*)+\Z")
SEMVER_RE = re.compile(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?\Z")
LICENSE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9.+-]{1,80}\Z")
TEMPLATE_VALUES = {"hfvi-leafer-frontend", "UNLICENSED"}
IDENTITY_FILES = (
    "README.md",
    "NOTICE",
    "VERSION",
    "CHANGELOG.md",
    "LICENSE",
    "local_extension_manifest.json",
    "openspec/project.md",
    "frontend/package.json",
    "frontend/package-lock.json",
    "frontend/index.html",
)


def _require_text(name: str, value: str, *, minimum: int = 1, maximum: int = 255) -> str:
    if not isinstance(value, str) or "\n" in value or "\r" in value:
        raise ValueError(f"{name} must be one line of text")
    value = value.strip()
    if not minimum <= len(value) <= maximum:
        raise ValueError(f"{name} must contain between {minimum} and {maximum} characters")
    if "{{" in value or "}}" in value or value in TEMPLATE_VALUES:
        raise ValueError(f"{name} contains an unresolved template value")
    return value


@dataclass(frozen=True)
class ProjectIdentity:
    project_id: str
    namespace: str
    display_name: str
    initial_version: str
    license_id: str
    copyright: str
    license_text: str

    @classmethod
    def create(
        cls,
        *,
        project_id: str,
        namespace: str,
        display_name: str,
        initial_version: str,
        license_id: str,
        copyright: str,
        license_text: str,
    ) -> "ProjectIdentity":
        project_id = _require_text("project_id", project_id, maximum=63)
        namespace = _require_text("namespace", namespace, maximum=253)
        display_name = _require_text("display_name", display_name, minimum=3, maximum=120)
        initial_version = _require_text("initial_version", initial_version, maximum=128)
        license_id = _require_text("license_id", license_id, minimum=2, maximum=82)
        copyright = _require_text("copyright", copyright, minimum=3, maximum=200)
        if not PROJECT_ID_RE.fullmatch(project_id):
            raise ValueError("project_id must use lowercase hyphenated identifiers")
        if not NAMESPACE_RE.fullmatch(namespace) or namespace.startswith("org.example."):
            raise ValueError("namespace must be a non-example dotted namespace")
        if not SEMVER_RE.fullmatch(initial_version):
            raise ValueError("initial_version must be a semantic version")
        if license_id == "UNLICENSED" or not LICENSE_ID_RE.fullmatch(license_id):
            raise ValueError("license_id must be a non-UNLICENSED SPDX-style identifier")
        if not isinstance(license_text, str) or len(license_text.strip()) < 32:
            raise ValueError("license_text must contain the selected license terms (at least 32 characters)")
        if "{{" in license_text or "UNLICENSED (template default)" in license_text:
            raise ValueError("license_text contains an unresolved template value")
        return cls(
            project_id=project_id,
            namespace=namespace,
            display_name=display_name,
            initial_version=initial_version,
            license_id=license_id,
            copyright=copyright,
            license_text=license_text.rstrip() + "\n",
        )

    @property
    def rendered_license(self) -> str:
        return (
            f"SPDX-License-Identifier: {self.license_id}\n"
            f"Copyright (c) {self.copyright}\n\n"
            f"{self.license_text}"
        )

    def document(self) -> dict[str, object]:
        rendered_license = self.rendered_license.encode("utf-8")
        return {
            "$schema": "https://das-standard.dev/schemas/project_identity.schema.json",
            "schemaVersion": "1.0.0",
            "projectId": self.project_id,
            "namespace": self.namespace,
            "displayName": self.display_name,
            "version": self.initial_version,
            "license": {
                "id": self.license_id,
                "copyright": self.copyright,
                "file": "LICENSE",
                "sha256": hashlib.sha256(rendered_license).hexdigest(),
            },
        }


def materialize_project_identity(repo_root: Path, identity: ProjectIdentity) -> None:
    """Render identity-bearing template files and bind the resulting repository."""
    replacements = {
        "{{PROJECT_ID}}": identity.project_id,
        "{{NAMESPACE}}": identity.namespace,
        "{{DISPLAY_NAME}}": identity.display_name,
        "{{INITIAL_VERSION}}": identity.initial_version,
        "{{LICENSE_ID}}": identity.license_id,
        "{{COPYRIGHT}}": identity.copyright,
        "{{LICENSE_TEXT}}": identity.license_text.rstrip(),
    }
    for relative_path in IDENTITY_FILES:
        path = repo_root / relative_path
        text = path.read_text(encoding="utf-8")
        for token, replacement in replacements.items():
            text = text.replace(token, replacement)
        if "{{" in text or "}}" in text:
            raise ValueError(f"identity rendering left an unresolved token in {relative_path}")
        path.write_text(text, encoding="utf-8")

    document = identity.document()
    (repo_root / "project_identity.json").write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    lock_path = repo_root / "tooling_lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    lock["projectIdentity"] = {
        "kind": "file",
        "uri": "./project_identity.json",
        "pinType": "sha256",
        "pinValue": hashlib.sha256(
            (repo_root / "project_identity.json").read_bytes()
        ).hexdigest(),
        "floating": False,
    }
    lock_path.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")
