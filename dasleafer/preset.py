from __future__ import annotations

from pathlib import Path
from typing import Optional

from .repo_factory import create_product_repo_from_template


def preset_template_dir(factory_root: Path) -> Path:
    return factory_root / "templates" / "das-leafer-product"


def create_product_repo(
    *,
    factory_root: Path,
    dest_dir: Path,
    master_doc_path: Path,
    ui_spec_path: Path,
    change_id: Optional[str] = None,
    intent: str = "",
    init_git: bool = True,
    overwrite: bool = False,
    change_empty: bool = False,
    project_id: str,
    namespace: str,
    display_name: str,
    initial_version: str,
    license_id: str,
    copyright: str,
    license_text: str,
) -> Path:
    return create_product_repo_from_template(
        template_dir=preset_template_dir(factory_root),
        dest_dir=dest_dir,
        master_doc_path=master_doc_path,
        ui_spec_path=ui_spec_path,
        change_id=change_id,
        intent=intent,
        init_git=init_git,
        overwrite=overwrite,
        change_empty=change_empty,
        project_id=project_id,
        namespace=namespace,
        display_name=display_name,
        initial_version=initial_version,
        license_id=license_id,
        copyright=copyright,
        license_text=license_text,
    )
