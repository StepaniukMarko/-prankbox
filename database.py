import aiosqlite, os
from config import DB_PATH

CATEGORIES_PAGES = {
    "categories": [
        # Page 1
        [("Кавказец 👳","👳",1),("Укр. язык №1 🇺🇦","🇺🇦",2),("Укр. язык №2 🇺🇦","🇺🇦",3),("Укр. язык №3 🇺🇦","🇺🇦",4),("Угрозы 🚨","🚨",5),("Разыграть девушку 🤷‍♀️","🤷‍♀️",6)],
        # Page 2
        [("Разыграть парня 🤷‍♂️","🤷‍♂️",7),("От бабки 👵","👵",8),("OLX 📝","📝",9),("Доставка 🚛","🚛",10),("Разное 👣","👣",11),("Гей 👬","👬",12)],
        # Page 3
        [("Полиция 👮","👮",13),("Глад Валакас 💩","💩",14),("Соседи 🏠","🏠",15),("Больница 🏥🇺🇦","🏥",16),("Водителям 🚗🇺🇦","🚗",17),("Halloween 🎃","🎃",18)],
        # Page 4
        [("Социальные сети 🖥️","🖥️",19),("Школа/Универ 👨‍🎓👩‍🎓","👨‍🎓",20),("Майнкрафтер 📦","📦",21),("Соседи 🏠🇺🇦","🏠",22),("Курильщикам 🚭","🚭",23),("Укр. язык №4 🇺🇦","🇺🇦",24)],
        # Page 5
        [("Ресторан и Кафе 🥐🇺🇦","🥐",25),("Водителям 🚗","🚗",26),("Такси 🚕","🚕",27),("Спорт ⚽","⚽",28)],
    ],
    "named": [
        [("Бумага 🧻👱‍♂️","🧻",29),("Бумага 🧻👩","🧻",30),("Опознайте друга 👱‍♂️","👱‍♂️",31),("Опознайте друга 👩","👩",32),("Девушка изменяет 💔","💔",33),("Курьер перепутал адрес 💐","💐",34),("Дочь не поздравил 😡","😡",35)],
    ],
    "holidays": [
        [("С Днем Рождения 🎁","🎁",36),("С Днем Рождения 🎁🇺🇦","🎁",37),("С 8 марта 🌷","🌷",38),("Новогодние 🎄","🎄",39),("С 14 февраля 💖","💖",40),("День Знаний 📚","📚",41)],
    ],
}

async def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER UNIQUE,
            username TEXT,
            first_name TEXT,
            balance INTEGER DEFAULT 0,
            referral_count INTEGER DEFAULT 0,
            referred_by INTEGER,
            created_at TEXT DEFAULT (datetime('now'))
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
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            file_id TEXT NOT NULL,
            category_id INTEGER,
            play_count INTEGER DEFAULT 0,
            hidden INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS favorites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            prank_id INTEGER,
            UNIQUE(user_id, prank_id)
        );
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER,
            referred_id INTEGER UNIQUE,
            created_at TEXT DEFAULT (datetime('now'))
        );
        """)
        # Seed categories
        for group, pages in CATEGORIES_PAGES.items():
            for page_idx, page in enumerate(pages):
                for sort_idx, (name, emoji, cat_id) in enumerate(page):
                    await db.execute(
                        "INSERT OR IGNORE INTO categories (id, name, emoji, group_name, page_num, sort_order) VALUES (?,?,?,?,?,?)",
                        (cat_id, name, emoji, group, page_idx, sort_idx)
                    )
        await db.commit()

async def get_db():
    return await aiosqlite.connect(DB_PATH)
