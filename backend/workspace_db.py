import sqlite3
import threading
from pathlib import Path

import yaml

from artists import is_placeholder_artist, normalize_artist_name
from platforms import _seed_known_aliases, _upsert_platform, normalize_platform_key
from utils import CONFIG_PATH, CONFIG_ROOT, utc_now_str
from runtime_context import WorkspaceContext, get_runtime_context


WORKSPACE_DB_PATH = CONFIG_ROOT / "data" / "workspace.db"
_WORKSPACE_SCHEMA_READY_PATHS: set[Path] = set()
_WORKSPACE_SCHEMA_LOCK = threading.Lock()


def _ctx(ctx: WorkspaceContext | None = None) -> WorkspaceContext:
    return ctx or get_runtime_context()


def _workspace_vault_db_paths(ctx: WorkspaceContext | None = None) -> list[Path]:
    runtime = _ctx(ctx)
    try:
        config = yaml.safe_load(runtime.config_path.read_text(encoding="utf-8")) or {}
    except OSError:
        config = {}
    vaults = config.get("vaults") if isinstance(config.get("vaults"), dict) else {}
    paths: list[Path] = []
    for entry in vaults.values():
        if not isinstance(entry, dict):
            continue
        root_value = str(entry.get("root") or "").strip()
        if not root_value:
            continue
        root = Path(root_value)
        root = root if root.is_absolute() else runtime.root / root
        db_path = root / "db" / "lmz_main.db"
        if db_path.exists():
            paths.append(db_path.resolve())
    return sorted(set(paths))


def ensure_workspace_schema(conn: sqlite3.Connection):
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS artists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            name_norm TEXT NOT NULL UNIQUE,
            kind TEXT NOT NULL DEFAULT 'artist',
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS artist_aliases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            artist_id INTEGER NOT NULL,
            alias TEXT NOT NULL,
            alias_norm TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            FOREIGN KEY(artist_id) REFERENCES artists(id) ON DELETE CASCADE
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS artist_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            artist_id INTEGER NOT NULL,
            platform TEXT NOT NULL,
            url TEXT NOT NULL,
            url_norm TEXT NOT NULL,
            handle TEXT NOT NULL DEFAULT '',
            is_primary INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(artist_id, url_norm),
            FOREIGN KEY(artist_id) REFERENCES artists(id) ON DELETE CASCADE
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_artists_name_norm ON artists(name_norm)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_artist_aliases_artist ON artist_aliases(artist_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_artist_aliases_norm ON artist_aliases(alias_norm)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_artist_links_artist ON artist_links(artist_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_artist_links_platform ON artist_links(platform)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_artist_links_url_norm ON artist_links(url_norm)")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS platforms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key_norm TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            kind TEXT NOT NULL DEFAULT 'source',
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS platform_aliases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform_id INTEGER NOT NULL,
            alias TEXT NOT NULL,
            alias_norm TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            FOREIGN KEY(platform_id) REFERENCES platforms(id) ON DELETE CASCADE
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_platforms_key_norm ON platforms(key_norm)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_platform_aliases_platform ON platform_aliases(platform_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_platform_aliases_norm ON platform_aliases(alias_norm)")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS wd_tag_dictionary (
            tag_norm TEXT PRIMARY KEY,
            tag TEXT NOT NULL,
            tag_type TEXT NOT NULL DEFAULT 'general',
            first_seen_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_wd_tag_dictionary_tag ON wd_tag_dictionary(tag)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_wd_tag_dictionary_type ON wd_tag_dictionary(tag_type)")


def upsert_wd_dictionary_tags(conn: sqlite3.Connection, tags: list[tuple[str, str]]):
    now = utc_now_str()
    rows = []
    seen = set()
    for tag_type, tag in tags:
        clean = str(tag or "").strip()
        tag_norm = " ".join(clean.casefold().split())
        clean_type = str(tag_type or "general").strip() or "general"
        if not clean or not tag_norm or tag_norm in seen:
            continue
        seen.add(tag_norm)
        rows.append((tag_norm, clean, clean_type, now, now))
    conn.executemany(
        """
        INSERT INTO wd_tag_dictionary(tag_norm, tag, tag_type, first_seen_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(tag_norm) DO UPDATE SET
            tag = excluded.tag,
            tag_type = excluded.tag_type,
            updated_at = excluded.updated_at
        """,
        rows,
    )


def backfill_workspace_metadata(conn: sqlite3.Connection, ctx: WorkspaceContext | None = None):
    ensure_workspace_schema(conn)
    now = utc_now_str()
    _upsert_platform(conn, "Local")
    _seed_known_aliases(conn)
    for db_path in _workspace_vault_db_paths(ctx):
        try:
            vault_conn = sqlite3.connect(db_path)
        except sqlite3.Error:
            continue
        try:
            artist_rows = vault_conn.execute("""
                SELECT DISTINCT TRIM(source_artist)
                FROM items
                WHERE source_artist IS NOT NULL AND TRIM(source_artist) != ''
            """).fetchall()
            artist_values = {}
            for (name,) in artist_rows:
                clean = str(name or "").strip()
                norm = normalize_artist_name(clean)
                if clean and norm and not is_placeholder_artist(clean):
                    artist_values.setdefault(norm, clean)
            conn.executemany(
                """
                INSERT OR IGNORE INTO artists(name, name_norm, kind, notes, created_at, updated_at)
                VALUES (?, ?, 'artist', '', ?, ?)
                """,
                [(name, norm, now, now) for norm, name in artist_values.items()],
            )

            platform_rows = vault_conn.execute("""
                SELECT DISTINCT TRIM(platform)
                FROM items
                WHERE platform IS NOT NULL AND TRIM(platform) != ''
            """).fetchall()
            for (platform,) in platform_rows:
                _upsert_platform(conn, str(platform or "").strip())

            try:
                wd_rows = vault_conn.execute("""
                    SELECT tag_type, tag
                    FROM item_wd_tags
                    WHERE tag IS NOT NULL AND TRIM(tag) != ''
                """).fetchall()
                upsert_wd_dictionary_tags(conn, [(row[0], row[1]) for row in wd_rows])
            except sqlite3.Error:
                pass
        except sqlite3.Error:
            continue
        finally:
            vault_conn.close()


def rebuild_workspace_metadata(ctx: WorkspaceContext | None = None) -> dict:
    conn = connect_workspace_database(ctx)
    try:
        before = _workspace_counts(conn)
        backfill_workspace_metadata(conn, ctx)
        conn.commit()
        after = _workspace_counts(conn)
        return {"status": "success", "before": before, "after": after}
    finally:
        conn.close()


def _workspace_usage(ctx: WorkspaceContext | None = None) -> dict[str, set[str]]:
    usage = {"artists": set(), "platforms": set(), "wd_tags": set()}
    for db_path in _workspace_vault_db_paths(ctx):
        try:
            vault_conn = sqlite3.connect(db_path)
        except sqlite3.Error:
            continue
        try:
            for (artist,) in vault_conn.execute("""
                SELECT DISTINCT LOWER(TRIM(source_artist))
                FROM items
                WHERE source_artist IS NOT NULL AND TRIM(source_artist) != ''
            """).fetchall():
                if artist:
                    usage["artists"].add(str(artist))
            for (platform,) in vault_conn.execute("""
                SELECT DISTINCT platform
                FROM items
                WHERE platform IS NOT NULL AND TRIM(platform) != ''
            """).fetchall():
                key = normalize_platform_key(platform)
                if key:
                    usage["platforms"].add(key)
            try:
                for (tag_norm,) in vault_conn.execute("""
                    SELECT DISTINCT tag_norm
                    FROM item_wd_tags
                    WHERE tag_norm IS NOT NULL AND TRIM(tag_norm) != ''
                """).fetchall():
                    if tag_norm:
                        usage["wd_tags"].add(str(tag_norm))
            except sqlite3.Error:
                pass
        except sqlite3.Error:
            continue
        finally:
            vault_conn.close()
    return usage


def _workspace_counts(conn: sqlite3.Connection) -> dict:
    return {
        "artists": conn.execute("SELECT COUNT(*) FROM artists").fetchone()[0],
        "platforms": conn.execute("SELECT COUNT(*) FROM platforms").fetchone()[0],
        "wd_tags": conn.execute("SELECT COUNT(*) FROM wd_tag_dictionary").fetchone()[0],
    }


def prune_unused_workspace_metadata(ctx: WorkspaceContext | None = None) -> dict:
    conn = connect_workspace_database(ctx)
    try:
        usage = _workspace_usage(ctx)
        before = _workspace_counts(conn)

        conn.execute(
            """
            DELETE FROM wd_tag_dictionary
            WHERE tag_norm NOT IN ({})
            """.format(",".join("?" for _ in usage["wd_tags"]) or "''"),
            tuple(usage["wd_tags"]),
        )

        deletable_artists = [
            row[0]
            for row in conn.execute(
                """
                SELECT artists.id
                FROM artists
                WHERE artists.name_norm NOT IN ({})
                  AND TRIM(artists.notes) = ''
                  AND NOT EXISTS (SELECT 1 FROM artist_aliases WHERE artist_aliases.artist_id = artists.id)
                  AND NOT EXISTS (SELECT 1 FROM artist_links WHERE artist_links.artist_id = artists.id)
                """.format(",".join("?" for _ in usage["artists"]) or "''"),
                tuple(usage["artists"]),
            ).fetchall()
        ]
        if deletable_artists:
            conn.execute(
                "DELETE FROM artists WHERE id IN ({})".format(",".join("?" for _ in deletable_artists)),
                tuple(deletable_artists),
            )

        deletable_platforms = [
            row[0]
            for row in conn.execute(
                """
                SELECT platforms.id
                FROM platforms
                WHERE platforms.key_norm != 'local'
                  AND platforms.key_norm NOT IN ({})
                  AND TRIM(platforms.notes) = ''
                  AND NOT EXISTS (SELECT 1 FROM platform_aliases WHERE platform_aliases.platform_id = platforms.id)
                """.format(",".join("?" for _ in usage["platforms"]) or "''"),
                tuple(usage["platforms"]),
            ).fetchall()
        ]
        if deletable_platforms:
            conn.execute(
                "DELETE FROM platforms WHERE id IN ({})".format(",".join("?" for _ in deletable_platforms)),
                tuple(deletable_platforms),
            )

        conn.commit()
        after = _workspace_counts(conn)
        return {
            "status": "success",
            "before": before,
            "after": after,
            "pruned": {key: before[key] - after[key] for key in before},
        }
    finally:
        conn.close()


def init_workspace_database(db_path: Path | None = None, ctx: WorkspaceContext | None = None):
    runtime = _ctx(ctx)
    target_path = Path(db_path or runtime.workspace_db_path).resolve()
    target_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target_path, timeout=5)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    ensure_workspace_schema(conn)
    backfill_workspace_metadata(conn, runtime)
    conn.commit()
    _WORKSPACE_SCHEMA_READY_PATHS.add(target_path)
    return conn


def connect_workspace_database(ctx: WorkspaceContext | None = None):
    target_path = _ctx(ctx).workspace_db_path.resolve()
    if target_path not in _WORKSPACE_SCHEMA_READY_PATHS or not target_path.exists():
        with _WORKSPACE_SCHEMA_LOCK:
            if target_path not in _WORKSPACE_SCHEMA_READY_PATHS or not target_path.exists():
                return init_workspace_database(target_path, ctx)
    conn = sqlite3.connect(target_path, timeout=5)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn
