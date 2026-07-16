"""
Módulo de base de datos - SQLite async
"""
import aiosqlite
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "bot.db")


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(
            """
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id       INTEGER PRIMARY KEY,
                log_channel_id INTEGER,
                prefix         TEXT DEFAULT '?'
            );

            CREATE TABLE IF NOT EXISTS welcome_settings (
                guild_id             INTEGER PRIMARY KEY,
                channel_id           INTEGER,
                message              TEXT DEFAULT '¡Bienvenido/a {user} a **{server}**!',
                embed_color          TEXT DEFAULT '#5865F2',
                image_url            TEXT,
                recommended_channels TEXT,
                dm_message           TEXT
            );

            CREATE TABLE IF NOT EXISTS automod_settings (
                guild_id        INTEGER PRIMARY KEY,
                enabled         INTEGER DEFAULT 1,
                flood_enabled   INTEGER DEFAULT 1,
                flood_threshold INTEGER DEFAULT 5,
                flood_interval  INTEGER DEFAULT 5,
                links_enabled   INTEGER DEFAULT 1,
                log_channel_id  INTEGER
            );

            CREATE TABLE IF NOT EXISTS automod_warnings (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id  INTEGER NOT NULL,
                user_id   INTEGER NOT NULL,
                reason    TEXT NOT NULL,
                timestamp TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS ticket_settings (
                guild_id         INTEGER PRIMARY KEY,
                panel_channel_id INTEGER,
                log_channel_id   INTEGER,
                panel_message    TEXT DEFAULT '¿Necesitas ayuda? Abre un ticket y te atenderemos lo antes posible.',
                open_type        TEXT DEFAULT 'button',
                support_role_id  INTEGER,
                category_id      INTEGER
            );

            CREATE TABLE IF NOT EXISTS ticket_categories (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id    INTEGER NOT NULL,
                name        TEXT NOT NULL,
                description TEXT DEFAULT '',
                emoji       TEXT DEFAULT '🎫'
            );

            CREATE TABLE IF NOT EXISTS tickets (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id    INTEGER NOT NULL,
                user_id     INTEGER NOT NULL,
                channel_id  INTEGER NOT NULL,
                category_id INTEGER,
                claimed_by  INTEGER,
                status      TEXT DEFAULT 'open',
                created_at  TEXT NOT NULL,
                closed_at   TEXT
            );

            CREATE TABLE IF NOT EXISTS mod_warnings (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id     INTEGER NOT NULL,
                user_id      INTEGER NOT NULL,
                moderator_id INTEGER NOT NULL,
                reason       TEXT NOT NULL,
                timestamp    TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS temp_bans (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id     INTEGER NOT NULL,
                user_id      INTEGER NOT NULL,
                moderator_id INTEGER NOT NULL,
                reason       TEXT,
                unban_at     TEXT NOT NULL,
                unbanned     INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS embed_menu_items (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id   INTEGER NOT NULL,
                guild_id     INTEGER NOT NULL,
                label        TEXT NOT NULL,
                description  TEXT,
                emoji        TEXT,
                response_msg TEXT NOT NULL
            );
            """
        )
        await db.commit()


# ─── Helper genérico upsert ──────────────────────────────────────────────────

async def _upsert(table: str, pk: str, pk_val: int, **kwargs):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(f"SELECT {pk} FROM {table} WHERE {pk} = ?", (pk_val,))
        if await cur.fetchone():
            sets = ", ".join(f"{k} = ?" for k in kwargs)
            await db.execute(f"UPDATE {table} SET {sets} WHERE {pk} = ?", (*kwargs.values(), pk_val))
        else:
            cols = f"{pk}, " + ", ".join(kwargs.keys())
            vals = "?, " + ", ".join("?" for _ in kwargs)
            await db.execute(f"INSERT INTO {table} ({cols}) VALUES ({vals})", (pk_val, *kwargs.values()))
        await db.commit()


async def _fetchone(table: str, pk: str, pk_val: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(f"SELECT * FROM {table} WHERE {pk} = ?", (pk_val,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


# ─── Guild settings ──────────────────────────────────────────────────────────

async def get_guild_settings(guild_id: int) -> dict | None:
    return await _fetchone("guild_settings", "guild_id", guild_id)


async def set_guild_settings(guild_id: int, **kwargs):
    await _upsert("guild_settings", "guild_id", guild_id, **kwargs)


# ─── Welcome settings ─────────────────────────────────────────────────────────

async def get_welcome_settings(guild_id: int) -> dict | None:
    return await _fetchone("welcome_settings", "guild_id", guild_id)


async def set_welcome_settings(guild_id: int, **kwargs):
    await _upsert("welcome_settings", "guild_id", guild_id, **kwargs)


async def reset_welcome_settings(guild_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM welcome_settings WHERE guild_id = ?", (guild_id,))
        await db.commit()


# ─── Automod settings ─────────────────────────────────────────────────────────

async def get_automod_settings(guild_id: int) -> dict | None:
    return await _fetchone("automod_settings", "guild_id", guild_id)


async def set_automod_settings(guild_id: int, **kwargs):
    await _upsert("automod_settings", "guild_id", guild_id, **kwargs)


async def add_warning(guild_id: int, user_id: int, reason: str):
    from datetime import datetime, timezone
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO automod_warnings (guild_id, user_id, reason, timestamp) VALUES (?,?,?,?)",
            (guild_id, user_id, reason, datetime.now(timezone.utc).isoformat()),
        )
        await db.commit()


async def get_warnings(guild_id: int, user_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM automod_warnings WHERE guild_id = ? AND user_id = ? ORDER BY id DESC",
            (guild_id, user_id),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


# ─── Mod warnings (moderación manual) ────────────────────────────────────────

async def add_mod_warning(guild_id: int, user_id: int, moderator_id: int, reason: str) -> int:
    from datetime import datetime, timezone
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO mod_warnings (guild_id, user_id, moderator_id, reason, timestamp) VALUES (?,?,?,?,?)",
            (guild_id, user_id, moderator_id, reason, datetime.now(timezone.utc).isoformat()),
        )
        await db.commit()
        return cur.lastrowid


async def get_mod_warnings(guild_id: int, user_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM mod_warnings WHERE guild_id = ? AND user_id = ? ORDER BY id DESC",
            (guild_id, user_id),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def count_mod_warnings(guild_id: int, user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM mod_warnings WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0


async def delete_mod_warning(warn_id: int, guild_id: int, user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "DELETE FROM mod_warnings WHERE id = ? AND guild_id = ? AND user_id = ?",
            (warn_id, guild_id, user_id),
        )
        await db.commit()
        return cur.rowcount > 0


# ─── Temp bans ────────────────────────────────────────────────────────────────

async def add_temp_ban(guild_id: int, user_id: int, moderator_id: int, reason: str | None, unban_at: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO temp_bans (guild_id, user_id, moderator_id, reason, unban_at) VALUES (?,?,?,?,?)",
            (guild_id, user_id, moderator_id, reason, unban_at),
        )
        await db.commit()
        return cur.lastrowid


async def get_pending_temp_bans() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM temp_bans WHERE unbanned = 0") as cur:
            return [dict(r) for r in await cur.fetchall()]


async def mark_temp_ban_done(ban_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE temp_bans SET unbanned = 1 WHERE id = ?", (ban_id,))
        await db.commit()


# ─── Embed menu items ─────────────────────────────────────────────────────────

async def save_embed_menu_items(message_id: int, guild_id: int, items: list[dict]) -> list[dict]:
    """Guarda todos los items de un menú y retorna la lista con sus IDs de BD."""
    result = []
    async with aiosqlite.connect(DB_PATH) as db:
        for item in items:
            cur = await db.execute(
                "INSERT INTO embed_menu_items (message_id, guild_id, label, description, emoji, response_msg) VALUES (?,?,?,?,?,?)",
                (message_id, guild_id, item["label"], item.get("description"), item.get("emoji"), item["response_msg"]),
            )
            result.append({**item, "id": cur.lastrowid})
        await db.commit()
    return result


async def get_embed_menu_items(message_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM embed_menu_items WHERE message_id = ? ORDER BY id ASC",
            (message_id,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_all_embed_menus() -> dict[int, list[dict]]:
    """Retorna todos los menús agrupados por message_id. Usado en cog_load para re-registrar vistas persistentes."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM embed_menu_items ORDER BY message_id, id ASC") as cur:
            rows = [dict(r) for r in await cur.fetchall()]
    result: dict[int, list[dict]] = {}
    for row in rows:
        result.setdefault(row["message_id"], []).append(row)
    return result


# ─── Ticket settings ──────────────────────────────────────────────────────────

async def get_ticket_settings(guild_id: int) -> dict | None:
    return await _fetchone("ticket_settings", "guild_id", guild_id)


async def set_ticket_settings(guild_id: int, **kwargs):
    await _upsert("ticket_settings", "guild_id", guild_id, **kwargs)


async def add_ticket_category(guild_id: int, name: str, description: str, emoji: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO ticket_categories (guild_id, name, description, emoji) VALUES (?,?,?,?)",
            (guild_id, name, description, emoji),
        )
        await db.commit()
        return cur.lastrowid


async def get_ticket_categories(guild_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM ticket_categories WHERE guild_id = ?", (guild_id,)) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def delete_ticket_category(category_id: int, guild_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM ticket_categories WHERE id = ? AND guild_id = ?",
            (category_id, guild_id),
        )
        await db.commit()


async def create_ticket(guild_id: int, user_id: int, channel_id: int, category_id: int | None) -> int:
    from datetime import datetime, timezone
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO tickets (guild_id, user_id, channel_id, category_id, created_at) VALUES (?,?,?,?,?)",
            (guild_id, user_id, channel_id, category_id, datetime.now(timezone.utc).isoformat()),
        )
        await db.commit()
        return cur.lastrowid


async def get_ticket_by_channel(channel_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM tickets WHERE channel_id = ?", (channel_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def update_ticket(channel_id: int, **kwargs):
    async with aiosqlite.connect(DB_PATH) as db:
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        await db.execute(f"UPDATE tickets SET {sets} WHERE channel_id = ?", (*kwargs.values(), channel_id))
        await db.commit()


async def get_open_ticket_by_user(guild_id: int, user_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM tickets WHERE guild_id = ? AND user_id = ? AND status != 'closed'",
            (guild_id, user_id),
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None
