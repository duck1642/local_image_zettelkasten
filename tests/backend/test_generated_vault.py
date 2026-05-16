import importlib
import importlib.util
import json
import os
import sqlite3
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
GENERATOR_PATH = ROOT / "tests" / "generators" / "generate_test_vault.py"


def load_generator():
    spec = importlib.util.spec_from_file_location("generate_test_vault_under_test", GENERATOR_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def reset_backend_modules():
    for name in list(sys.modules):
        if name in {"utils", "web_api", "metadata_index", "md_generator", "thumbnails"} or name.startswith(("db.", "logger", "tagging")):
            del sys.modules[name]


def assert_inside(path: Path, root: Path):
    assert path.resolve().is_relative_to(root.resolve())


def test_generated_vault_smoke_and_isolation(tmp_path, monkeypatch):
    generator = load_generator()
    generated_root = tmp_path / "generated"
    output = generated_root / "001-smoke"
    generator.main([
        "--output", str(output),
        "--generated-root", str(generated_root),
        "--items", "100",
        "--groups", "12",
        "--review", "4",
        "--video-ratio", "0.2",
        "--artists", "8",
        "--topics", "9",
        "--seed", "7",
    ])

    config_path = output / "config.yaml"
    manifest_path = output / "manifest.json"
    db_path = output / "data" / "db" / "lmz_main.db"
    assert config_path.exists()
    assert manifest_path.exists()
    assert db_path.exists()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["counts"]["items"] == 100
    assert manifest["counts"]["review"] == 4
    assert manifest["counts"]["videos"] > 0

    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    for value in config["paths"].values():
        assert_inside(output / value, output)

    conn = sqlite3.connect(db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 100
    finally:
        conn.close()

    for relative in [
        "data/logs/structured/system.jsonl",
        "data/logs/structured/auth.jsonl",
        "data/logs/structured/review.jsonl",
        "data/logs/structured/ingest_local.jsonl",
        "data/logs/structured/ingest_online.jsonl",
        "data/logs/structured/ingestion_audit.jsonl",
        "data/logs/raw/terminal.log",
    ]:
        assert (output / relative).exists()

    monkeypatch.setenv("LMZ_CONFIG_PATH", str(config_path))
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))
    reset_backend_modules()
    utils = importlib.import_module("utils")
    sqlite_operator = importlib.import_module("db.sqlite_operator")
    thumbnails = importlib.import_module("thumbnails")

    assert utils.DB_PATH == db_path
    assert utils.LOGS_DIR == output / "data" / "logs"
    assert utils.THUMBNAILS_DIR == output / "data" / "ui_cache" / "thumbnails"
    assert thumbnails.THUMBNAIL_DIR == utils.THUMBNAILS_DIR
    conn = sqlite_operator.connect_database()
    try:
        assert conn.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 100
    finally:
        conn.close()


def test_generated_vault_rows_notes_and_media_are_consistent(tmp_path):
    generator = load_generator()
    generated_root = tmp_path / "generated"
    output = generated_root / "001-consistency"
    generator.main([
        "--output", str(output),
        "--generated-root", str(generated_root),
        "--items", "40",
        "--groups", "5",
        "--review", "2",
        "--video-ratio", "0.35",
        "--seed", "11",
    ])

    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    conn = sqlite3.connect(output / "data" / "db" / "lmz_main.db")
    try:
        samples = [manifest["items"][0], manifest["items"][7], next(item for item in manifest["items"] if item["mime_type"] == "video/mp4")]
        for item in samples:
            row = conn.execute(
                "SELECT storage_id, file_extension, mime_type, source_url, platform, source_artist FROM items WHERE hash = ?",
                (item["hash"],),
            ).fetchone()
            assert row == (
                item["storage_id"],
                item["extension"],
                item["mime_type"],
                item["source_url"],
                item["platform"],
                item["artist"],
            )

            shard = item["hash"][:2]
            asset_path = output / "data" / "vault" / "assets" / shard / f"{item['storage_id']}{item['extension']}"
            note_path = output / "data" / "vault" / "notes" / shard / f"{item['storage_id']}.md"
            suffix = "_video" if item["mime_type"].startswith("video/") else ""
            thumb_path = output / "data" / "ui_cache" / "thumbnails" / shard / f"{item['storage_id']}{suffix}.jpg"
            assert asset_path.exists()
            assert note_path.exists()
            assert thumb_path.exists()

            frontmatter = yaml.safe_load(note_path.read_text(encoding="utf-8").split("---", 2)[1])
            assert frontmatter["hash"] == item["hash"]
            assert frontmatter["storage_id"] == item["storage_id"]
            assert frontmatter["source_url"] == item["source_url"]
            assert frontmatter["platform"] == item["platform"]
            assert frontmatter["source_artist"] == item["artist"]
            assert frontmatter["topics"] == item["topics"]
    finally:
        conn.close()


def test_generated_vault_refuses_runtime_paths(tmp_path):
    generator = load_generator()
    generated_root = tmp_path / "generated"
    for dangerous in [ROOT, ROOT / "data", ROOT / "config", ROOT / "logs", ROOT / "secrets"]:
        try:
            generator.main(["--output", str(dangerous), "--generated-root", str(generated_root)])
        except SystemExit as exc:
            assert exc.code != 0
        else:
            raise AssertionError(f"dangerous path was accepted: {dangerous}")


def test_generated_vault_auto_numbers_outputs(tmp_path):
    generator = load_generator()
    generated_root = tmp_path / "generated"
    generator.main(["--generated-root", str(generated_root), "--name", "small", "--items", "3", "--review", "0"])
    generator.main(["--generated-root", str(generated_root), "--name", "video mix", "--items", "3", "--review", "0"])

    assert (generated_root / "001-small").exists()
    assert (generated_root / "002-video-mix").exists()
