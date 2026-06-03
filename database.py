import asyncpg
import os
import logging
from config import CATEGORIES_PAGES

DATABASE_URL = os.getenv("DATABASE_URL", "")

pool = None
logger = logging.getLogger(__name__)


async def init_db():
    """Initialize database pool and create tables."""
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    async with pool.acquire() as conn:
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT UNIQUE NOT NULL,
            username TEXT,
            first_name TEXT,
            balance INTEGER DEFAULT 0,
            referral_count INTEGER DEFAULT 0,
            referred_by BIGINT,
            created_at TIMESTAMP DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            emoji TEXT,
            group_name TEXT DEFAULT 'categories',
            page_num INTEGER DEFAULT 0,
            sort_order INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS pranks (
            id SERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            file_id TEXT NOT NULL UNIQUE,
            category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
            play_count INTEGER DEFAULT 0,
            hidden INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS favorites (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            prank_id INTEGER NOT NULL REFERENCES pranks(id) ON DELETE CASCADE,
            created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(user_id, prank_id)
        );

        CREATE TABLE IF NOT EXISTS referrals (
            id SERIAL PRIMARY KEY,
            referrer_id BIGINT NOT NULL,
            referred_id BIGINT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        );

        CREATE INDEX IF NOT EXISTS idx_pranks_category ON pranks(category_id);
        CREATE INDEX IF NOT EXISTS idx_pranks_play_count ON pranks(play_count DESC);
        CREATE INDEX IF NOT EXISTS idx_favorites_user ON favorites(user_id);
        CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id);
        """)

        # Seed categories (idempotent — won't duplicate)
        for group, pages in CATEGORIES_PAGES.items():
            for page_idx, page in enumerate(pages):
                for sort_idx, (name, emoji, cat_id) in enumerate(page):
                    await conn.execute(
                        """INSERT INTO categories (id, name, emoji, group_name, page_num, sort_order)
                           VALUES ($1, $2, $3, $4, $5, $6)
                           ON CONFLICT (id) DO UPDATE SET
                               name = EXCLUDED.name,
                               emoji = EXCLUDED.emoji,
                               group_name = EXCLUDED.group_name,
                               page_num = EXCLUDED.page_num,
                               sort_order = EXCLUDED.sort_order""",
                        cat_id, name, emoji, group, page_idx, sort_idx
                    )

    logger.info("✅ Database initialized successfully")


async def get_pool():
    """Get the database connection pool."""
    return pool


# ─── USER OPERATIONS ───────────────────────────────────────────────

async def ensure_user(telegram_id: int, username: str = None, first_name: str = None, ref_id: int = None):
    """Register user if not exists, handle referral bonus."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT 1 FROM users WHERE telegram_id=$1", telegram_id)
        if not row:
            await conn.execute(
                "INSERT INTO users (telegram_id, username, first_name) VALUES ($1, $2, $3)",
                telegram_id, username, first_name
            )
            if ref_id and ref_id != telegram_id:
                await conn.execute(
                    "INSERT INTO referrals (referrer_id, referred_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                    ref_id, telegram_id
                )
                await conn.execute(
                    "UPDATE users SET referral_count = referral_count + 1, balance = balance + $1 WHERE telegram_id = $2",
                    10, ref_id  # REFERRAL_BONUS
                )


async def get_user(telegram_id: int):
    """Get user data."""
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT telegram_id, username, first_name, balance, referral_count, created_at FROM users WHERE telegram_id=$1",
            telegram_id
        )


# ─── CATEGORY OPERATIONS ──────────────────────────────────────────

async def get_page_categories(group: str, page: int):
    """Get categories for a specific group page."""
    pages = CATEGORIES_PAGES.get(group, [])
    if page < 0 or page >= len(pages):
        return [], 0
    ids = [c[2] for c in pages[page]]
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, name, emoji FROM categories WHERE id = ANY($1) ORDER BY sort_order",
            ids
        )
    return [{"id": r["id"], "name": r["name"], "emoji": r["emoji"]} for r in rows], len(pages)


async def get_all_categories():
    """Get all categories for admin panel."""
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT id, name, emoji FROM categories ORDER BY group_name, page_num, sort_order")
    return [{"id": r["id"], "name": r["name"], "emoji": r["emoji"]} for r in rows]


# ─── PRANK OPERATIONS ─────────────────────────────────────────────

async def get_pranks_by_category(cat_id: int):
    """Get all non-hidden pranks in a category."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, title, play_count FROM pranks WHERE category_id=$1 AND hidden=0 ORDER BY id",
            cat_id
        )
    return [(r["id"], r["title"], r["play_count"]) for r in rows]


async def get_prank(prank_id: int):
    """Get a single prank by ID."""
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM pranks WHERE id=$1", prank_id)


async def get_top_pranks(limit: int = 10):
    """Get top pranks by play count."""
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT id, title, play_count, category_id FROM pranks WHERE hidden=0 AND play_count > 0 ORDER BY play_count DESC LIMIT $1",
            limit
        )


async def get_random_pranks(limit: int = 3):
    """Get random non-hidden pranks."""
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT id, title, file_id, play_count FROM pranks WHERE hidden=0 ORDER BY RANDOM() LIMIT $1",
            limit
        )


async def increment_play_count(prank_id: int):
    """Increment play count and return file_id + title."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE pranks SET play_count = play_count + 1 WHERE id=$1 RETURNING file_id, title, play_count",
            prank_id
        )
    return row


async def add_prank(title: str, file_id: str, category_id: int):
    """Add new prank (skip if file_id already exists)."""
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(
                "INSERT INTO pranks (title, file_id, category_id) VALUES ($1, $2, $3) RETURNING id",
                title, file_id, category_id
            )
            return row["id"] if row else None
        except asyncpg.UniqueViolationError:
            logger.info(f"Prank with file_id already exists, skipping: {title}")
            return None


async def delete_prank(prank_id: int):
    """Delete prank and its favorites."""
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM favorites WHERE prank_id=$1", prank_id)
        await conn.execute("DELETE FROM pranks WHERE id=$1", prank_id)


async def rename_prank(prank_id: int, new_title: str):
    """Rename a prank."""
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE pranks SET title=$1, updated_at=NOW() WHERE id=$2",
            new_title, prank_id
        )


async def change_prank_category(prank_id: int, cat_id: int):
    """Change prank category."""
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE pranks SET category_id=$1, updated_at=NOW() WHERE id=$2",
            cat_id, prank_id
        )


# ─── FAVORITES OPERATIONS ─────────────────────────────────────────

async def add_favorite(user_id: int, prank_id: int) -> bool:
    """Add to favorites. Returns True if added, False if already exists."""
    async with pool.acquire() as conn:
        try:
            await conn.execute(
                "INSERT INTO favorites (user_id, prank_id) VALUES ($1, $2)",
                user_id, prank_id
            )
            return True
        except asyncpg.UniqueViolationError:
            return False


async def get_favorites(user_id: int):
    """Get user's favorite pranks."""
    async with pool.acquire() as conn:
        return await conn.fetch(
            """SELECT p.id, p.title, p.file_id, p.play_count
               FROM favorites f JOIN pranks p ON f.prank_id = p.id
               WHERE f.user_id = $1 ORDER BY f.created_at DESC""",
            user_id
        )


async def get_favorites_count(user_id: int) -> int:
    """Get count of user favorites."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT COUNT(*) as cnt FROM favorites WHERE user_id=$1", user_id)
        return row["cnt"] if row else 0


# ─── STATS OPERATIONS ─────────────────────────────────────────────

async def get_bot_stats():
    """Get general bot statistics."""
    async with pool.acquire() as conn:
        users = await conn.fetchval("SELECT COUNT(*) FROM users")
        pranks = await conn.fetchval("SELECT COUNT(*) FROM pranks WHERE hidden=0")
        plays = await conn.fetchval("SELECT COALESCE(SUM(play_count), 0) FROM pranks")
        categories = await conn.fetchval("SELECT COUNT(*) FROM categories")
    return {
        "users": users or 0,
        "pranks": pranks or 0,
        "plays": plays or 0,
        "categories": categories or 0,
    }


# ─── ADMIN OPERATIONS ─────────────────────────────────────────────

async def get_all_users_ids():
    """Get all user telegram IDs for broadcast."""
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT telegram_id FROM users")
    return [r["telegram_id"] for r in rows]


async def get_pranks_paginated(offset: int = 0, limit: int = 10):
    """Get pranks with pagination for admin."""
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT id, title, category_id, play_count FROM pranks ORDER BY id DESC LIMIT $1 OFFSET $2",
            limit, offset
        )


async def get_category_name(cat_id: int) -> str:
    """Get category name by ID."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT name FROM categories WHERE id=$1", cat_id)
    return row["name"] if row else "—"


async def get_category_info(cat_id: int):
    """Get category group and page info."""
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT group_name, page_num FROM categories WHERE id=$1", cat_id)
