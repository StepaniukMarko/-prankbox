import asyncpg
import os
from config import CATEGORIES_PAGES

DATABASE_URL = os.getenv("DATABASE_URL", "")

pool = None

async def init_db():
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    async with pool.acquire() as conn:
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT UNIQUE,
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
            file_id TEXT NOT NULL,
            category_id INTEGER,
            play_count INTEGER DEFAULT 0,
            hidden INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS favorites (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            prank_id INTEGER,
            UNIQUE(user_id, prank_id)
        );
        CREATE TABLE IF NOT EXISTS referrals (
            id SERIAL PRIMARY KEY,
            referrer_id BIGINT,
            referred_id BIGINT UNIQUE,
            created_at TIMESTAMP DEFAULT NOW()
        );
        """)
        # Seed categories (INSERT ON CONFLICT DO NOTHING)
        for group, pages in CATEGORIES_PAGES.items():
            for page_idx, page in enumerate(pages):
                for sort_idx, (name, emoji, cat_id) in enumerate(page):
                    await conn.execute(
                        "INSERT INTO categories (id, name, emoji, group_name, page_num, sort_order) VALUES ($1,$2,$3,$4,$5,$6) ON CONFLICT (id) DO NOTHING",
                        cat_id, name, emoji, group, page_idx, sort_idx
                    )

async def get_pool():
    return pool
