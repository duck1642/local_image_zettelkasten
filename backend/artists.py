import sqlite3
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from utils import utc_now_str
from platforms import normalize_platform_key, resolve_platform_label


VALID_ARTIST_KINDS = {"artist", "real_person", "brand", "other"}
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
        clean_kind = "other"
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





def _active_artist_counts(item_conn: sqlite3.Connection, artist_conn: sqlite3.Connection, rows: list[sqlite3.Row | tuple]) -> dict[int, int]:
    counts = {int(row[0]): 0 for row in rows}
    if not rows:
        return counts
    norm_to_artist: dict[str, int] = {}
    artist_ids = []
    for row in rows:
        artist_id = int(row[0])
        name_norm = str(row[3])
        artist_ids.append(artist_id)
        if name_norm:
            norm_to_artist[name_norm] = artist_id
    if artist_ids:
        placeholders = ",".join("?" for _ in artist_ids)
        for alias_norm, alias_artist_id in artist_conn.execute(
            f"SELECT alias_norm, artist_id FROM artist_aliases WHERE artist_id IN ({placeholders})",
            tuple(artist_ids),
        ).fetchall():
            if alias_norm:
                norm_to_artist[str(alias_norm)] = int(alias_artist_id)
    for artist_value, count in item_conn.execute("""
        SELECT LOWER(TRIM(source_artist)), COUNT(*)
        FROM items
        WHERE source_artist IS NOT NULL AND TRIM(source_artist) != ''
        GROUP BY LOWER(TRIM(source_artist))
    """).fetchall():
        artist_id = norm_to_artist.get(str(artist_value or ""))
        if artist_id is not None:
            counts[artist_id] = counts.get(artist_id, 0) + int(count or 0)
    return counts


def list_artists(conn: sqlite3.Connection, q: str = "", limit: int = 100, used_only: bool = False, item_conn: sqlite3.Connection | None = None) -> list[dict]:
    ensure_artist_schema(conn, backfill=False)
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
            artists.name_norm,
            (SELECT COUNT(*) FROM artist_links WHERE artist_links.artist_id = artists.id) AS link_count,
            (SELECT COUNT(*) FROM artist_aliases WHERE artist_aliases.artist_id = artists.id) AS alias_count
        FROM artists
        {where}
        ORDER BY artists.name COLLATE NOCASE ASC
        LIMIT ?
        """,
        (*params, limit),
    ).fetchall()
    counts = _active_artist_counts(item_conn or conn, conn, rows)
    items = [
        {
            "id": row[0],
            "name": row[1],
            "kind": row[2],
            "item_count": counts.get(int(row[0]), 0),
            "link_count": row[4],
            "alias_count": row[5],
        }
        for row in rows
    ]
    if used_only:
        items = [item for item in items if int(item["item_count"] or 0) > 0]
    return items


def get_artist_detail(conn: sqlite3.Connection, artist_id: int, item_conn: sqlite3.Connection | None = None) -> dict | None:
    ensure_artist_schema(conn, backfill=False)
    row = conn.execute(
        """
        SELECT id, name, name_norm, kind, notes
        FROM artists
        WHERE id = ?
        """,
        (artist_id,),
    ).fetchone()
    if row is None:
        return None
    # _active_artist_counts expects index [3] = name_norm; SELECT order is id, name, name_norm, kind, notes
    counts = _active_artist_counts(item_conn or conn, conn, [(row[0], row[1], row[3], row[2])])
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
        "item_count": counts.get(int(row[0]), 0),
        "aliases": aliases,
        "links": links,
    }


def update_artist(conn: sqlite3.Connection, artist_id: int, name: str | None = None, kind: str | None = None, notes: str | None = None, item_conn: sqlite3.Connection | None = None) -> dict:
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
    detail = get_artist_detail(conn, artist_id, item_conn=item_conn)
    if detail is None:
        raise KeyError("artist not found")
    return detail


def _load_artist_row(conn: sqlite3.Connection, artist_id: int) -> dict | None:
    row = conn.execute(
        "SELECT id, name, name_norm, kind, notes FROM artists WHERE id = ?",
        (artist_id,),
    ).fetchone()
    if row is None:
        return None
    return {"id": row[0], "name": row[1], "name_norm": row[2], "kind": row[3], "notes": row[4]}


def _artist_alias_rows(conn: sqlite3.Connection, artist_id: int) -> list[dict]:
    return [
        {"id": row[0], "artist_id": artist_id, "alias": row[1], "alias_norm": row[2]}
        for row in conn.execute(
            "SELECT id, alias, alias_norm FROM artist_aliases WHERE artist_id = ? ORDER BY alias COLLATE NOCASE",
            (artist_id,),
        ).fetchall()
    ]


def _artist_link_rows(conn: sqlite3.Connection, artist_id: int) -> list[dict]:
    return [
        {
            "id": row[0],
            "artist_id": artist_id,
            "platform": row[1],
            "url": row[2],
            "url_norm": row[3],
            "handle": row[4],
            "is_primary": bool(row[5]),
        }
        for row in conn.execute(
            """
            SELECT id, platform, url, url_norm, handle, is_primary
            FROM artist_links
            WHERE artist_id = ?
            ORDER BY is_primary DESC, platform COLLATE NOCASE, url COLLATE NOCASE
            """,
            (artist_id,),
        ).fetchall()
    ]


def _merge_context(conn: sqlite3.Connection, target_id: int, source_artist_ids: list[int]) -> dict:
    ensure_artist_schema(conn, backfill=False)
    source_ids = []
    seen = set()
    for raw_id in source_artist_ids or []:
        source_id = int(raw_id)
        if source_id not in seen:
            seen.add(source_id)
            source_ids.append(source_id)
    if not source_ids:
        raise ValueError("at least one source artist is required")
    if int(target_id) in seen:
        raise ValueError("target artist cannot be a source")
    target = _load_artist_row(conn, int(target_id))
    if target is None:
        raise KeyError("target artist not found")
    if is_placeholder_artist(target["name"]):
        raise ValueError("placeholder artists cannot be merge targets")
    sources = []
    for source_id in source_ids:
        source = _load_artist_row(conn, source_id)
        if source is None:
            raise KeyError("source artist not found")
        if is_placeholder_artist(source["name"]):
            raise ValueError("placeholder artists cannot be merge sources")
        sources.append(source)
    return {"target": target, "sources": sources}


def preview_artist_merge(conn: sqlite3.Connection, target_id: int, source_artist_ids: list[int], item_conn: sqlite3.Connection | None = None) -> dict:
    context = _merge_context(conn, target_id, source_artist_ids)
    target = context["target"]
    sources = context["sources"]
    source_ids = [source["id"] for source in sources]
    source_id_set = set(source_ids)

    target_alias_rows = _artist_alias_rows(conn, target["id"])
    target_norms = {target["name_norm"], *(row["alias_norm"] for row in target_alias_rows)}
    source_aliases_by_id = {source["id"]: _artist_alias_rows(conn, source["id"]) for source in sources}
    source_norms = {source["name_norm"] for source in sources}
    for aliases in source_aliases_by_id.values():
        source_norms.update(alias["alias_norm"] for alias in aliases)

    artist_owner = {
        row[0]: row[1]
        for row in conn.execute("SELECT name_norm, id FROM artists").fetchall()
    }
    alias_owner = {
        row[0]: row[1]
        for row in conn.execute("SELECT alias_norm, artist_id FROM artist_aliases").fetchall()
    }

    aliases_to_add = []
    aliases_to_move = []
    alias_duplicates = []
    alias_conflicts = []
    candidate_norms = set()

    def consider_alias(value: str, value_norm: str, source_id: int, mode: str):
        if not value or not value_norm or value_norm == target["name_norm"]:
            alias_duplicates.append({"value": value, "reason": "target name"})
            return
        if value_norm in target_norms or value_norm in candidate_norms:
            alias_duplicates.append({"value": value, "reason": "duplicate"})
            return
        owner_artist = artist_owner.get(value_norm)
        if owner_artist is not None and owner_artist != source_id:
            alias_conflicts.append({"value": value, "reason": "artist name conflict"})
            return
        owner_alias = alias_owner.get(value_norm)
        if owner_alias is not None and owner_alias not in source_id_set and owner_alias != target["id"]:
            alias_conflicts.append({"value": value, "reason": "alias conflict"})
            return
        candidate_norms.add(value_norm)
        row = {"value": value, "value_norm": value_norm, "source_artist_id": source_id}
        if mode == "move":
            aliases_to_move.append(row)
        else:
            aliases_to_add.append(row)

    for source in sources:
        consider_alias(source["name"], source["name_norm"], source["id"], "add")
        for alias in source_aliases_by_id[source["id"]]:
            consider_alias(alias["alias"], alias["alias_norm"], source["id"], "move")

    target_link_norms = {link["url_norm"] for link in _artist_link_rows(conn, target["id"])}
    seen_link_norms = set(target_link_norms)
    links_to_move = []
    duplicate_links = []
    for source in sources:
        for link in _artist_link_rows(conn, source["id"]):
            if link["url_norm"] in seen_link_norms:
                duplicate_links.append({"id": link["id"], "url": link["url"], "source_artist_id": source["id"]})
                continue
            seen_link_norms.add(link["url_norm"])
            links_to_move.append({"id": link["id"], "url": link["url"], "source_artist_id": source["id"]})

    placeholders = ",".join("?" for _ in source_norms)
    affected_item_count = 0
    if source_norms:
        affected_item_count = conn.execute(
            f"SELECT COUNT(*) FROM items WHERE LOWER(TRIM(source_artist)) IN ({placeholders})",
            tuple(source_norms),
        ).fetchone()[0] if item_conn is None else item_conn.execute(
            f"SELECT COUNT(*) FROM items WHERE LOWER(TRIM(source_artist)) IN ({placeholders})",
            tuple(source_norms),
        ).fetchone()[0]

    notes_appended = sum(1 for source in sources if str(source.get("notes") or "").strip())
    return {
        "target": {"id": target["id"], "name": target["name"]},
        "sources": [{"id": source["id"], "name": source["name"]} for source in sources],
        "affected_items": affected_item_count,
        "aliases": {
            "add": aliases_to_add,
            "move": aliases_to_move,
            "duplicates": alias_duplicates,
            "conflicts": alias_conflicts,
        },
        "links": {
            "move": links_to_move,
            "duplicates": duplicate_links,
        },
        "notes_appended": notes_appended,
        "source_artists_deleted": len(sources),
        "source_norms": sorted(source_norms),
        "facet_norms": sorted(source_norms | {target["name_norm"]}),
    }


def merge_artists(conn: sqlite3.Connection, target_id: int, source_artist_ids: list[int], item_conn: sqlite3.Connection | None = None) -> dict:
    preview = preview_artist_merge(conn, target_id, source_artist_ids, item_conn=item_conn)
    target = _load_artist_row(conn, int(target_id))
    if target is None:
        raise KeyError("target artist not found")
    source_ids = [source["id"] for source in preview["sources"]]
    now = utc_now_str()

    if preview["source_norms"]:
        placeholders = ",".join("?" for _ in preview["source_norms"])
        query_conn = item_conn or conn
        item_hashes = [
            row[0]
            for row in query_conn.execute(
                f"SELECT hash FROM items WHERE LOWER(TRIM(source_artist)) IN ({placeholders})",
                tuple(preview["source_norms"]),
            ).fetchall()
        ]
    else:
        item_hashes = []

    for alias in preview["aliases"]["add"]:
        conn.execute(
            """
            INSERT OR IGNORE INTO artist_aliases(artist_id, alias, alias_norm, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (target["id"], alias["value"], alias["value_norm"], now),
        )
    for alias in preview["aliases"]["move"]:
        conn.execute(
            "UPDATE artist_aliases SET artist_id = ? WHERE alias_norm = ? AND artist_id IN ({})".format(
                ",".join("?" for _ in source_ids)
            ),
            (target["id"], alias["value_norm"], *source_ids),
        )

    for link in preview["links"]["move"]:
        conn.execute("UPDATE artist_links SET artist_id = ?, updated_at = ? WHERE id = ?", (target["id"], now, link["id"]))
    for link in preview["links"]["duplicates"]:
        conn.execute("DELETE FROM artist_links WHERE id = ?", (link["id"],))

    if item_hashes:
        (item_conn or conn).executemany(
            "UPDATE items SET source_artist = ? WHERE hash = ?",
            [(target["name"], item_hash) for item_hash in item_hashes],
        )

    target_notes = str(target.get("notes") or "").rstrip()
    note_chunks = [target_notes] if target_notes else []
    for source in preview["sources"]:
        row = _load_artist_row(conn, source["id"])
        source_notes = str((row or {}).get("notes") or "").strip()
        if source_notes:
            note_chunks.append(f"--- merged from {source['name']} ---\n{source_notes}")
    if note_chunks:
        conn.execute(
            "UPDATE artists SET notes = ?, updated_at = ? WHERE id = ?",
            ("\n\n".join(note_chunks), now, target["id"]),
        )

    if source_ids:
        placeholders = ",".join("?" for _ in source_ids)
        conn.execute(f"DELETE FROM artist_aliases WHERE artist_id IN ({placeholders})", tuple(source_ids))
        conn.execute(f"DELETE FROM artist_links WHERE artist_id IN ({placeholders})", tuple(source_ids))
        conn.execute(f"DELETE FROM artists WHERE id IN ({placeholders})", tuple(source_ids))

    result = dict(preview)
    result["item_hashes"] = item_hashes
    result["target_detail"] = get_artist_detail(conn, target["id"], item_conn=item_conn)
    result["merged"] = True
    return result


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
