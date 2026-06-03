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

        CREATE TABLE IF NOT EXISTS referrals (
            id SERIAL PRIMARY KEY,
            referrer_id BIGINT NOT NULL,
            referred_id BIGINT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS prank_calls (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            username TEXT,
            phone_number TEXT NOT NULL,
            prank_id INTEGER REFERENCES pranks(id) ON DELETE SET NULL,
            status TEXT DEFAULT 'pending_payment',
            payment_id TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            completed_at TIMESTAMP,
            recording_url TEXT,
            call_duration INTEGER DEFAULT 0
        );

        CREATE INDEX IF NOT EXISTS idx_pranks_category ON pranks(category_id);
        CREATE INDEX IF NOT EXISTS idx_pranks_play_count ON pranks(play_count DESC);
        CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id);
        CREATE INDEX IF NOT EXISTS idx_prank_calls_user ON prank_calls(user_id);
        CREATE INDEX IF NOT EXISTS idx_prank_calls_status ON prank_calls(status);
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


async def get_pranks_by_category_page(cat_id: int, offset: int = 0, limit: int = 10):
    """Get paginated pranks in a category with file_id for playback."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, title, file_id, play_count FROM pranks WHERE category_id=$1 AND hidden=0 ORDER BY id LIMIT $2 OFFSET $3",
            cat_id, limit, offset
        )
        count_row = await conn.fetchval(
            "SELECT COUNT(*) FROM pranks WHERE category_id=$1 AND hidden=0",
            cat_id
        )
    return rows, count_row or 0


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
    """Delete prank."""
    async with pool.acquire() as conn:
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


# ─── PRANK CALLS OPERATIONS ───────────────────────────────────────

async def create_prank_call(user_id: int, username: str, phone_number: str, prank_id: int) -> int:
    """Create a new prank call order. Returns the call ID."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO prank_calls (user_id, username, phone_number, prank_id, status)
               VALUES ($1, $2, $3, $4, 'pending_payment') RETURNING id""",
            user_id, username, phone_number, prank_id
        )
    return row["id"]


async def update_call_payment(call_id: int, payment_id: str):
    """Mark call as paid."""
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE prank_calls SET status='paid', payment_id=$1 WHERE id=$2",
            payment_id, call_id
        )


async def update_call_status(call_id: int, status: str):
    """Update call status (calling, completed, failed)."""
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE prank_calls SET status=$1 WHERE id=$2",
            status, call_id
        )


async def complete_call(call_id: int, duration: int, recording_url: str = None):
    """Mark call as completed with duration and optional recording."""
    async with pool.acquire() as conn:
        await conn.execute(
            """UPDATE prank_calls 
               SET status='completed', completed_at=NOW(), call_duration=$1, recording_url=$2 
               WHERE id=$3""",
            duration, recording_url, call_id
        )


async def fail_call(call_id: int, reason: str = None):
    """Mark call as failed."""
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE prank_calls SET status='failed', completed_at=NOW() WHERE id=$1",
            call_id
        )


async def get_prank_call(call_id: int):
    """Get prank call by ID."""
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM prank_calls WHERE id=$1", call_id)


async def get_pranks_for_calls(offset: int = 0, limit: int = 10):
    """Get all available pranks for call menu (paginated)."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, title, file_id FROM pranks WHERE hidden=0 ORDER BY id LIMIT $1 OFFSET $2",
            limit, offset
        )
        count = await conn.fetchval("SELECT COUNT(*) FROM pranks WHERE hidden=0")
    return rows, count or 0


async def get_calls_stats():
    """Get prank calls statistics for admin."""
    async with pool.acquire() as conn:
        total = await conn.fetchval("SELECT COUNT(*) FROM prank_calls")
        paid = await conn.fetchval("SELECT COUNT(*) FROM prank_calls WHERE status != 'pending_payment'")
        completed = await conn.fetchval("SELECT COUNT(*) FROM prank_calls WHERE status = 'completed'")
        failed = await conn.fetchval("SELECT COUNT(*) FROM prank_calls WHERE status = 'failed'")
        revenue = await conn.fetchval("SELECT COUNT(*) FROM prank_calls WHERE payment_id IS NOT NULL")
    return {
        "total": total or 0,
        "paid": paid or 0,
        "completed": completed or 0,
        "failed": failed or 0,
        "revenue_stars": (revenue or 0) * 79,
    }
