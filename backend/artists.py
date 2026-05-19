import sqlite3
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from utils import utc_now_str
from platforms import normalize_platform_key, resolve_platform_label


VALID_ARTIST_KINDS = {"artist", "real_person"}
PLACEHOLDER_ARTIST_NORMS = {"", "unknown", "local", "none", "n/a", "na", "null"}


def normalize_artist_name(value: str) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def is_placeholder_artist(value: str) -> bool:
    return normalize_artist_name(value) in PLACEHOLDER_ARTIST_NORMS


def normalize_artist_url(url: str) -> str:
    raw = str(url or "").strip()
    if not raw:
        return ""
    try:
        parsed = urlsplit(raw if "://" in raw else f"https://{raw}")
    except ValueError:
        return raw.casefold()
    scheme = (parsed.scheme or "https").casefold()
    host = parsed.netloc.casefold()
    path = parsed.path.rstrip("/")
    query = urlencode(sorted(parse_qsl(parsed.query, keep_blank_values=True)))
    return urlunsplit((scheme, host, path, query, ""))


def extract_artist_handle(platform: str, url: str) -> str:
    platform = normalize_platform_key(platform)
    try:
        parsed = urlsplit(url if "://" in url else f"https://{url}")
    except ValueError:
        return ""
    host = parsed.netloc.casefold()
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if platform == "x" and parts:
        return parts[0].lstrip("@")
    if platform == "pixiv":
        if "pixiv.net" in host and "users" in parts:
            index = parts.index("users")
            if index + 1 < len(parts):
                return parts[index + 1]
        return parts[-1] if parts else ""
    if platform == "fanbox":
        if host.endswith(".fanbox.cc"):
            return host.removesuffix(".fanbox.cc")
        return parts[0] if parts else ""
    if platform in {"instagram", "bluesky", "deviantart", "artstation", "patreon", "onlyfans", "fansly"} and parts:
        return parts[0].lstrip("@")
    return parts[-1].lstrip("@") if parts else ""


def ensure_artist_schema(conn: sqlite3.Connection, backfill: bool = True):
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
    if backfill:
        backfill_artists_from_items(conn)


def backfill_artists_from_items(conn: sqlite3.Connection):
    now = utc_now_str()
    rows = conn.execute("""
        SELECT DISTINCT TRIM(source_artist)
        FROM items
        WHERE source_artist IS NOT NULL AND TRIM(source_artist) != ''
    """).fetchall()
    names_by_norm = {}
    for (name,) in rows:
        clean_name = str(name or "").strip()
        name_norm = normalize_artist_name(clean_name)
        if clean_name and name_norm and not is_placeholder_artist(clean_name) and name_norm not in names_by_norm:
            names_by_norm[name_norm] = clean_name
    conn.executemany(
        """
        INSERT OR IGNORE INTO artists(name, name_norm, kind, notes, created_at, updated_at)
        VALUES (?, ?, 'artist', '', ?, ?)
        """,
        [(name, name_norm, now, now) for name_norm, name in names_by_norm.items()],
    )


def ensure_artist_for_name(conn: sqlite3.Connection, name: str, kind: str = "artist"):
    return resolve_artist_name(conn, name, kind=kind, create=True)


def resolve_artist_name(conn: sqlite3.Connection, name: str, kind: str = "artist", create: bool = True) -> str:
    clean_name = str(name or "").strip()
    name_norm = normalize_artist_name(clean_name)
    if not clean_name or not name_norm:
        return ""
    if is_placeholder_artist(clean_name):
        return clean_name
    ensure_artist_schema(conn, backfill=False)
    row = conn.execute("SELECT name FROM artists WHERE name_norm = ?", (name_norm,)).fetchone()
    if row:
        return str(row[0])
    row = conn.execute(
        """
        SELECT artists.name
        FROM artist_aliases
        JOIN artists ON artists.id = artist_aliases.artist_id
        WHERE artist_aliases.alias_norm = ?
        """,
        (name_norm,),
    ).fetchone()
    if row:
        return str(row[0])
    if not create:
        return clean_name
    clean_kind = str(kind or "artist").strip().casefold()
    if clean_kind not in VALID_ARTIST_KINDS:
        clean_kind = "artist"
    now = utc_now_str()
    conn.execute(
        """
        INSERT OR IGNORE INTO artists(name, name_norm, kind, notes, created_at, updated_at)
        VALUES (?, ?, ?, '', ?, ?)
        """,
        (clean_name, name_norm, clean_kind, now, now),
    )
    return clean_name


def _artist_exists(conn: sqlite3.Connection, artist_id: int) -> bool:
    return conn.execute("SELECT 1 FROM artists WHERE id = ?", (artist_id,)).fetchone() is not None


def _item_count_sql() -> str:
    return """
        SELECT COUNT(*)
        FROM items
        WHERE LOWER(TRIM(source_artist)) = artists.name_norm
           OR LOWER(TRIM(source_artist)) IN (
               SELECT alias_norm FROM artist_aliases WHERE artist_aliases.artist_id = artists.id
           )
    """


def list_artists(conn: sqlite3.Connection, q: str = "", limit: int = 100) -> list[dict]:
    ensure_artist_schema(conn, backfill=True)
    needle = normalize_artist_name(q)
    limit = max(1, min(int(limit or 100), 500))
    params: list = []
    where = ""
    if needle:
        where = """
            WHERE artists.name_norm LIKE ?
               OR artists.id IN (SELECT artist_id FROM artist_aliases WHERE alias_norm LIKE ?)
        """
        params.extend([f"%{needle}%", f"%{needle}%"])
    rows = conn.execute(
        f"""
        SELECT
            artists.id,
            artists.name,
            artists.kind,
            ({_item_count_sql()}) AS item_count,
            (SELECT COUNT(*) FROM artist_links WHERE artist_links.artist_id = artists.id) AS link_count,
            (SELECT COUNT(*) FROM artist_aliases WHERE artist_aliases.artist_id = artists.id) AS alias_count
        FROM artists
        {where}
        ORDER BY item_count DESC, artists.name COLLATE NOCASE ASC
        LIMIT ?
        """,
        (*params, limit),
    ).fetchall()
    return [
        {
            "id": row[0],
            "name": row[1],
            "kind": row[2],
            "item_count": row[3],
            "link_count": row[4],
            "alias_count": row[5],
        }
        for row in rows
    ]


def get_artist_detail(conn: sqlite3.Connection, artist_id: int) -> dict | None:
    ensure_artist_schema(conn, backfill=False)
    row = conn.execute(
        f"""
        SELECT id, name, name_norm, kind, notes, ({_item_count_sql()}) AS item_count
        FROM artists
        WHERE id = ?
        """,
        (artist_id,),
    ).fetchone()
    if row is None:
        return None
    aliases = [
        {"id": alias_id, "alias": alias, "alias_norm": alias_norm}
        for alias_id, alias, alias_norm in conn.execute(
            "SELECT id, alias, alias_norm FROM artist_aliases WHERE artist_id = ? ORDER BY alias COLLATE NOCASE",
            (artist_id,),
        ).fetchall()
    ]
    links = [
        {"id": link_id, "platform": platform, "url": url, "handle": handle, "is_primary": bool(is_primary)}
        for link_id, platform, url, handle, is_primary in conn.execute(
            """
            SELECT id, platform, url, handle, is_primary
            FROM artist_links
            WHERE artist_id = ?
            ORDER BY is_primary DESC, platform COLLATE NOCASE, url COLLATE NOCASE
            """,
            (artist_id,),
        ).fetchall()
    ]
    return {
        "id": row[0],
        "name": row[1],
        "name_norm": row[2],
        "kind": row[3],
        "notes": row[4],
        "item_count": row[5],
        "aliases": aliases,
        "links": links,
    }


def update_artist(conn: sqlite3.Connection, artist_id: int, name: str | None = None, kind: str | None = None, notes: str | None = None) -> dict:
    ensure_artist_schema(conn, backfill=False)
    if not _artist_exists(conn, artist_id):
        raise KeyError("artist not found")
    updates = []
    params = []
    if name is not None:
        clean_name = str(name or "").strip()
        name_norm = normalize_artist_name(clean_name)
        if not clean_name or not name_norm:
            raise ValueError("artist name is required")
        if is_placeholder_artist(clean_name):
            raise ValueError("placeholder artist names cannot be canonical records")
        duplicate = conn.execute("SELECT 1 FROM artists WHERE name_norm = ? AND id != ?", (name_norm, artist_id)).fetchone()
        if duplicate:
            raise FileExistsError("artist name already exists")
        updates.extend(["name = ?", "name_norm = ?"])
        params.extend([clean_name, name_norm])
    if kind is not None:
        clean_kind = str(kind or "").strip().casefold()
        if clean_kind not in VALID_ARTIST_KINDS:
            raise ValueError("invalid artist kind")
        updates.append("kind = ?")
        params.append(clean_kind)
    if notes is not None:
        updates.append("notes = ?")
        params.append(str(notes or ""))
    if updates:
        updates.append("updated_at = ?")
        params.append(utc_now_str())
        params.append(artist_id)
        conn.execute(f"UPDATE artists SET {', '.join(updates)} WHERE id = ?", params)
    detail = get_artist_detail(conn, artist_id)
    if detail is None:
        raise KeyError("artist not found")
    return detail


def add_artist_alias(conn: sqlite3.Connection, artist_id: int, alias: str) -> dict:
    ensure_artist_schema(conn, backfill=False)
    if not _artist_exists(conn, artist_id):
        raise KeyError("artist not found")
    clean_alias = str(alias or "").strip()
    alias_norm = normalize_artist_name(clean_alias)
    if not clean_alias or not alias_norm:
        raise ValueError("alias is required")
    if is_placeholder_artist(clean_alias):
        raise ValueError("placeholder artist names cannot be aliases")
    if conn.execute("SELECT 1 FROM artists WHERE name_norm = ?", (alias_norm,)).fetchone():
        raise FileExistsError("alias conflicts with artist name")
    if conn.execute("SELECT 1 FROM artist_aliases WHERE alias_norm = ?", (alias_norm,)).fetchone():
        raise FileExistsError("alias already exists")
    now = utc_now_str()
    cursor = conn.execute(
        "INSERT INTO artist_aliases(artist_id, alias, alias_norm, created_at) VALUES (?, ?, ?, ?)",
        (artist_id, clean_alias, alias_norm, now),
    )
    return {"id": cursor.lastrowid, "alias": clean_alias, "alias_norm": alias_norm}


def delete_artist_alias(conn: sqlite3.Connection, artist_id: int, alias_id: int) -> bool:
    ensure_artist_schema(conn, backfill=False)
    cursor = conn.execute("DELETE FROM artist_aliases WHERE artist_id = ? AND id = ?", (artist_id, alias_id))
    return cursor.rowcount > 0


def add_artist_link(conn: sqlite3.Connection, artist_id: int, platform: str, url: str, handle: str | None = None, is_primary: bool = False) -> dict:
    ensure_artist_schema(conn, backfill=False)
    if not _artist_exists(conn, artist_id):
        raise KeyError("artist not found")
    clean_platform = resolve_platform_label(conn, platform)
    clean_url = str(url or "").strip()
    url_norm = normalize_artist_url(clean_url)
    if not clean_platform:
        raise ValueError("platform is required")
    if not clean_url or not url_norm:
        raise ValueError("url is required")
    clean_handle = str(handle or "").strip() or extract_artist_handle(clean_platform, clean_url)
    now = utc_now_str()
    try:
        cursor = conn.execute(
            """
            INSERT INTO artist_links(artist_id, platform, url, url_norm, handle, is_primary, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (artist_id, clean_platform, clean_url, url_norm, clean_handle, 1 if is_primary else 0, now, now),
        )
    except sqlite3.IntegrityError as exc:
        raise FileExistsError("artist link already exists") from exc
    return {
        "id": cursor.lastrowid,
        "platform": clean_platform,
        "url": clean_url,
        "handle": clean_handle,
        "is_primary": bool(is_primary),
    }


def delete_artist_link(conn: sqlite3.Connection, artist_id: int, link_id: int) -> bool:
    ensure_artist_schema(conn, backfill=False)
    cursor = conn.execute("DELETE FROM artist_links WHERE artist_id = ? AND id = ?", (artist_id, link_id))
    return cursor.rowcount > 0
