import sqlite3
import sys
import zipfile
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import vault_packages


def test_manifest_requires_strict_package_shape():
    manifest = vault_packages.build_manifest(
        package_type=vault_packages.EXPORT_PACKAGE_TYPE,
        source_vault_id="default",
        source_vault_name="Default",
        contents={"assets": True, "notes": True, "db": True},
        item_count=3,
        file_count=9,
    )

    assert manifest["package_version"] == vault_packages.PACKAGE_VERSION
    assert manifest["source_vault"]["id"] == "default"

    with pytest.raises(vault_packages.VaultPackageError, match="unsupported package type"):
        vault_packages.validate_manifest({**manifest, "package_type": "zip"})

    bad_paths = {**manifest, "source_path": "C:/Users/example/vault"}
    with pytest.raises(vault_packages.VaultPackageError, match="absolute path"):
        vault_packages.validate_manifest(bad_paths)


def test_archive_member_validation_rejects_unsafe_paths(tmp_path):
    package = tmp_path / "bad.zip"
    manifest = vault_packages.build_manifest(
        package_type=vault_packages.EXPORT_PACKAGE_TYPE,
        source_vault_id="default",
        source_vault_name="Default",
        contents={"assets": True},
        item_count=0,
        file_count=1,
    )
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr(vault_packages.MANIFEST_NAME, yaml.safe_dump(manifest))
        archive.writestr("../escape.txt", "bad")

    with zipfile.ZipFile(package, "r") as archive:
        vault_packages.load_manifest_from_archive(archive, expected_type=vault_packages.EXPORT_PACKAGE_TYPE)
        with pytest.raises(vault_packages.VaultPackageError, match="unsafe archive path"):
            vault_packages.validate_archive_members(archive, allowed_roots={"vault", "db"})


def test_archive_member_validation_rejects_unsupported_roots(tmp_path):
    package = tmp_path / "bad-root.zip"
    manifest = vault_packages.build_manifest(
        package_type=vault_packages.EXPORT_PACKAGE_TYPE,
        source_vault_id="default",
        source_vault_name="Default",
        contents={"assets": True},
        item_count=0,
        file_count=1,
    )
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr(vault_packages.MANIFEST_NAME, yaml.safe_dump(manifest))
        archive.writestr("logs/raw/system.log", "not portable")

    with zipfile.ZipFile(package, "r") as archive:
        with pytest.raises(vault_packages.VaultPackageError, match="unsupported archive path"):
            vault_packages.validate_archive_members(archive, allowed_roots={"vault", "db"})


def test_fingerprint_and_sqlite_snapshot(tmp_path):
    source_db = tmp_path / "source.db"
    target_db = tmp_path / "snapshot.db"
    conn = sqlite3.connect(source_db)
    conn.execute("CREATE TABLE example(id INTEGER PRIMARY KEY, value TEXT)")
    conn.execute("INSERT INTO example(value) VALUES ('ok')")
    conn.commit()
    conn.close()

    vault_packages.snapshot_sqlite_database(source_db, target_db)

    copied = sqlite3.connect(target_db)
    try:
        assert copied.execute("SELECT value FROM example").fetchone()[0] == "ok"
    finally:
        copied.close()
    assert vault_packages.package_fingerprint(source_db) == vault_packages.package_fingerprint(source_db)


def test_package_operation_lock_is_exclusive():
    with vault_packages.package_operation_lock("workspace"):
        with pytest.raises(vault_packages.VaultPackageError, match="already running"):
            with vault_packages.package_operation_lock("workspace"):
                pass
