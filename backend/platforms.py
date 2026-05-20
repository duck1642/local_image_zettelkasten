import sqlite3

from utils import utc_now_str


KNOWN_PLATFORM_ALIASES = {
    "local": "local",
    "pixiv": "pixiv",
    "pixiv.net": "pixiv",
    "instagram": "instagram",
    "instagram.com": "instagram",
    "pinterest": "pinterest",
    "pinterest.com": "pinterest",
    "pin.it": "pinterest",
    "youtube": "youtube",
    "youtube.com": "youtube",
    "youtu.be": "youtube",
    "x": "x",
    "x.com": "x",
    "twitter": "x",
    "twitter.com": "x",
    "twitter1": "x",
    "twitter2": "x",
    "pixiv_fanbox": "fanbox",
    "pixiv fanbox": "fanbox",
    "fanbox": "fanbox",
    "fanbox.cc": "fanbox",
}

KNOWN_PLATFORM_DISPLAY = {
    "local": "Local",
    "pixiv": "Pixiv",
    "instagram": "Instagram",
    "pinterest": "Pinterest",
    "youtube": "YouTube",
    "x": "X",
    "fanbox": "Fanbox",
}


def normalize_platform_key(value: str) -> str:
    text = str(value or "").strip().casefold()
    if not text:
        return ""
    text = text.removeprefix("https://").removeprefix("http://").removeprefix("www.")
    text = text.rstrip("/")
    simple = text.replace("-", "_").replace("_", " ").replace(".", ".")
    key = text.replace("-", "_")
    return KNOWN_PLATFORM_ALIASES.get(text) or KNOWN_PLATFORM_ALIASES.get(key) or KNOWN_PLATFORM_ALIASES.get(simple) or key


def display_for_platform_key(key_norm: str, fallback: str = "") -> str:
    key_norm = normalize_platform_key(key_norm)
    if key_norm in KNOWN_PLATFORM_DISPLAY:
        return KNOWN_PLATFORM_DISPLAY[key_norm]
    clean = str(fallback or "").strip()
    return clean or key_norm


def ensure_platform_schema(conn: sqlite3.Connection, backfill: bool = True):
    cursor = conn.cursor()
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
    if backfill:
        _upsert_platform(conn, "Local")
        backfill_platforms_from_items(conn)
        _seed_known_aliases(conn)


def _upsert_platform(conn: sqlite3.Connection, label: str, kind: str = "source") -> str:
    clean = str(label or "").strip()
    key_norm = normalize_platform_key(clean)
    if not clean or not key_norm:
        return ""
    display = display_for_platform_key(key_norm, clean)
    now = utc_now_str()
    conn.execute(
        """
        INSERT OR IGNORE INTO platforms(key_norm, display_name, kind, notes, created_at, updated_at)
        VALUES (?, ?, ?, '', ?, ?)
        """,
        (key_norm, display, kind, now, now),
    )
    return display


def _platform_id_for_key(conn: sqlite3.Connection, key_norm: str) -> int | None:
    row = conn.execute("SELECT id FROM platforms WHERE key_norm = ?", (key_norm,)).fetchone()
    return int(row[0]) if row else None


def _seed_known_aliases(conn: sqlite3.Connection):
    now = utc_now_str()
    for alias, key_norm in KNOWN_PLATFORM_ALIASES.items():
        platform_id = _platform_id_for_key(conn, key_norm)
        alias_norm = normalize_platform_key(alias)
        if platform_id and alias_norm and alias_norm != key_norm:
            conn.execute(
                """
                INSERT OR IGNORE INTO platform_aliases(platform_id, alias, alias_norm, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (platform_id, alias, alias_norm, now),
            )


def backfill_platforms_from_items(conn: sqlite3.Connection):
    rows = conn.execute("""
        SELECT DISTINCT TRIM(platform)
        FROM items
        WHERE platform IS NOT NULL AND TRIM(platform) != ''
    """).fetchall()
    for (platform,) in rows:
        _upsert_platform(conn, str(platform or "").strip())


def resolve_platform_label(conn: sqlite3.Connection, value: str, create: bool = True) -> str:
    clean = str(value or "").strip()
    key_norm = normalize_platform_key(clean)
    if not clean or not key_norm:
        return ""
    ensure_platform_schema(conn, backfill=False)
    row = conn.execute("SELECT display_name FROM platforms WHERE key_norm = ?", (key_norm,)).fetchone()
    if row:
        return str(row[0])
    row = conn.execute(
        """
        SELECT platforms.display_name
        FROM platform_aliases
        JOIN platforms ON platforms.id = platform_aliases.platform_id
        WHERE platform_aliases.alias_norm = ?
        """,
        (key_norm,),
    ).fetchone()
    if row:
        return str(row[0])
    if create:
        return _upsert_platform(conn, clean)
    return clean


def list_platforms(conn: sqlite3.Connection, q: str = "", limit: int = 100, used_only: bool = False, item_conn: sqlite3.Connection | None = None) -> list[dict]:
    ensure_platform_schema(conn, backfill=False)
    needle = str(q or "").strip().casefold()
    limit = max(1, min(int(limit or 100), 500))
    item_counts: dict[str, int] = {}
    count_conn = item_conn or conn
    for platform, count in count_conn.execute("""
        SELECT platform, COUNT(*)
        FROM items
        WHERE platform IS NOT NULL AND TRIM(platform) != ''
        GROUP BY platform
    """).fetchall():
        key = normalize_platform_key(platform)
        if key:
            item_counts[key] = item_counts.get(key, 0) + int(count)
    rows = conn.execute(
        """
        SELECT
            platforms.id,
            platforms.key_norm,
            platforms.display_name,
            platforms.kind,
            (SELECT COUNT(*) FROM platform_aliases WHERE platform_aliases.platform_id = platforms.id) AS alias_count
        FROM platforms
        ORDER BY display_name COLLATE NOCASE ASC
        """
    ).fetchall()
    items = []
    for row in rows:
        display = str(row[2])
        key_norm = str(row[1])
        if needle and needle not in display.casefold() and needle not in key_norm:
            continue
        item_count = item_counts.get(key_norm, 0)
        if used_only and item_count <= 0:
            continue
        items.append({
            "id": row[0],
            "key_norm": key_norm,
            "display_name": display,
            "kind": row[3],
            "item_count": item_count,
            "alias_count": row[4],
        })
    items.sort(key=lambda item: (-int(item["item_count"]), str(item["display_name"]).casefold()))
    return items[:limit]
