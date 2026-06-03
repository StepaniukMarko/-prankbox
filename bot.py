import asyncio, logging, random
from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import Message, CallbackQuery, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import BOT_TOKEN, ADMIN_IDS, REFERRAL_BONUS
from database import init_db, get_pool, CATEGORIES_PAGES
from keyboards import main_menu, pranks_menu, category_page_kb, prank_card_kb, admin_cat_kb, admin_prank_kb

from aiogram.fsm.storage.memory import MemoryStorage

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)

pending_audio = {}  # admin pending uploads
user_pages = {}     # user_id -> {group: page}

# === FSM STATES ===
class AddAudio(StatesGroup):
    waiting_title = State()
    waiting_category = State()

class RenameAudio(StatesGroup):
    waiting_new_title = State()

# === HELPERS ===
async def ensure_user(msg, ref_id=None):
    pool = await get_pool()
    async with pool.acquire() as db:
        row = await db.fetchrow("SELECT 1 FROM users WHERE telegram_id=$1", msg.from_user.id)
        if not row:
            await db.execute("INSERT INTO users (telegram_id, username, first_name) VALUES ($1,$2,$3)",
                             msg.from_user.id, msg.from_user.username, msg.from_user.first_name)
            if ref_id and ref_id != msg.from_user.id:
                await db.execute("INSERT INTO referrals (referrer_id, referred_id) VALUES ($1,$2) ON CONFLICT DO NOTHING", ref_id, msg.from_user.id)
                await db.execute("UPDATE users SET referral_count=referral_count+1, balance=balance+$1 WHERE telegram_id=$2", REFERRAL_BONUS, ref_id)

async def get_page_cats(group: str, page: int):
    from config import CATEGORIES_PAGES
    pages = CATEGORIES_PAGES.get(group, [])
    if page < 0 or page >= len(pages): return [], 0
    pool = await get_pool()
    async with pool.acquire() as db:
        ids = [c[2] for c in pages[page]]
        rows = await db.fetch("SELECT id, name FROM categories WHERE id = ANY($1) ORDER BY sort_order", ids)
    return [{"id": r["id"], "name": r["name"]} for r in rows], len(pages)

async def get_pranks_in_cat(cat_id: int):
    pool = await get_pool()
    async with pool.acquire() as db:
        rows = await db.fetch("SELECT id, title, play_count FROM pranks WHERE category_id=$1 AND hidden=0 ORDER BY id", cat_id)
    return [(r["id"], r["title"], r["play_count"]) for r in rows]

# === COMMANDS ===
@router.message(Command("start"))
async def cmd_start(msg: Message):
    ref_id = None
    if msg.text and "ref_" in msg.text:
        try: ref_id = int(msg.text.split("ref_")[1])
        except: pass
    await ensure_user(msg, ref_id)
    await msg.answer("🎉 Ласкаво просимо до <b>PrankBox</b>!\n\nОбирай розіграш та відправляй друзям 😆", parse_mode="HTML", reply_markup=main_menu())

@router.message(Command("profile"))
@router.message(F.text == "👤 Мій акаунт")
async def cmd_profile(msg: Message):
    await ensure_user(msg)
    db = await get_db()
    cur = await db.execute("SELECT telegram_id, username, balance, referral_count, created_at FROM users WHERE telegram_id=?", (msg.from_user.id,))
    u = await cur.fetchone()
    fav = await db.execute("SELECT COUNT(*) FROM favorites WHERE user_id=?", (msg.from_user.id,))
    fc = (await fav.fetchone())[0]
    await db.close()
    await msg.answer(
        f"👤 <b>Мій акаунт</b>\n\n"
        f"🆔 ID: <code>{u[0]}</code>\n"
        f"👤 Username: @{u[1] or 'не вказано'}\n"
        f"📅 Реєстрація: {u[4]}\n"
        f"💰 Баланс: {u[2]} монет\n"
        f"👥 Рефералів: {u[3]}\n"
        f"❤️ Обране: {fc}", parse_mode="HTML"
    )

@router.message(Command("faq"))
@router.message(F.text == "❓ FAQ")
async def cmd_faq(msg: Message):
    await msg.answer(
        "❓ <b>FAQ</b>\n\n"
        "🎵 <b>Як слухати?</b>\nОбери категорію → натисни ▶ Слухати\n\n"
        "❤️ <b>Обране?</b>\nНатисни ❤️ під аудіо\n\n"
        "💸 <b>Реферали?</b>\nЗапрошуй друзів і отримуй монети\n\n"
        "📞 <b>Підтримка:</b> @admin", parse_mode="HTML"
    )

@router.message(Command("top10"))
@router.message(F.text == "🏆 ТОП 10")
async def cmd_top10(msg: Message):
    db = await get_db()
    cur = await db.execute("SELECT id, title, play_count, category_id FROM pranks WHERE hidden=0 ORDER BY play_count DESC LIMIT 10")
    rows = await cur.fetchall()
    await db.close()
    if not rows:
        return await msg.answer("🏆 Поки що немає аудіо в рейтингу.")
    text = "🏆 <b>ТОП 10</b>\n\n"
    for i, r in enumerate(rows, 1):
        text += f"{i}. 🎵 <b>{r[1]}</b>\n   ▶ {r[2]} прослуховувань\n\n"
    await msg.answer(text, parse_mode="HTML")

@router.message(Command("ref"))
@router.message(F.text == "💸 Заробити")
async def cmd_earn(msg: Message):
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start=ref_{msg.from_user.id}"
    db = await get_db()
    cur = await db.execute("SELECT referral_count, balance FROM users WHERE telegram_id=?", (msg.from_user.id,))
    u = await cur.fetchone()
    await db.close()
    await msg.answer(
        f"💸 <b>Заробити монети</b>\n\n"
        f"Запрошуй друзів і отримуй +{REFERRAL_BONUS} монет!\n\n"
        f"🔗 Твоє посилання:\n<code>{link}</code>\n\n"
        f"👥 Запрошено: {u[0] if u else 0}\n"
        f"💰 Баланс: {u[1] if u else 0}", parse_mode="HTML"
    )

@router.message(Command("pay"))
@router.message(F.text == "💰 Поповнити баланс")
async def cmd_pay(msg: Message):
    await msg.answer("💰 <b>Поповнення балансу</b>\n\nНаразі доступне через реферальну систему.\nЗапрошуйте друзів!", parse_mode="HTML")

# === PRANKS MENU ===
@router.message(F.text == "😆 Розіграші")
async def menu_pranks(msg: Message):
    await msg.answer("😆 Обери розділ:", reply_markup=pranks_menu())

@router.message(F.text == "🏁 Головне меню")
async def menu_main(msg: Message):
    await msg.answer("🏠 Головне меню", reply_markup=main_menu())

@router.message(F.text == "📝 Категорії")
async def menu_cats(msg: Message):
    user_pages[msg.from_user.id] = {"categories": 0}
    cats, total = await get_page_cats("categories", 0)
    await msg.answer("📝 <b>Категорії</b> (стор. 1):", parse_mode="HTML", reply_markup=category_page_kb(cats, 0, total, "categories"))

@router.message(F.text == "👦👩 Іменні")
async def menu_named(msg: Message):
    cats, total = await get_page_cats("named", 0)
    await msg.answer("👦👩 <b>Іменні</b>:", parse_mode="HTML", reply_markup=category_page_kb(cats, 0, total, "named"))

@router.message(F.text == "🎉 Свята")
async def menu_holidays(msg: Message):
    cats, total = await get_page_cats("holidays", 0)
    await msg.answer("🎉 <b>Свята</b>:", parse_mode="HTML", reply_markup=category_page_kb(cats, 0, total, "holidays"))

@router.message(F.text == "🌀 Випадкові записи")
async def menu_random(msg: Message):
    db = await get_db()
    cur = await db.execute("SELECT id, title, file_id, play_count FROM pranks WHERE hidden=0 ORDER BY RANDOM() LIMIT 3")
    rows = await cur.fetchall()
    await db.close()
    if not rows:
        return await msg.answer("📭 Поки що немає аудіо.")
    for r in rows:
        await msg.answer_audio(r[2], caption=f"🎵 <b>{r[1]}</b>\n▶ {r[3]} прослуховувань", parse_mode="HTML")

@router.message(F.text == "❤️ Обране")
async def menu_fav(msg: Message):
    db = await get_db()
    cur = await db.execute("SELECT p.id, p.title, p.file_id, p.play_count FROM favorites f JOIN pranks p ON f.prank_id=p.id WHERE f.user_id=?", (msg.from_user.id,))
    rows = await cur.fetchall()
    await db.close()
    if not rows:
        return await msg.answer("❤️ У вас поки немає обраних.")
    for r in rows[:10]:
        await msg.answer_audio(r[2], caption=f"❤️ <b>{r[1]}</b>\n▶ {r[3]} прослуховувань", parse_mode="HTML")

# === PAGINATION CALLBACKS ===
@router.callback_query(F.data.startswith("pg_"))
async def cb_page(cb: CallbackQuery):
    parts = cb.data.split("_")
    group = parts[1]
    page = int(parts[2])
    cats, total = await get_page_cats(group, page)
    if not cats:
        return await cb.answer("Немає більше сторінок")
    await cb.message.edit_text(f"📝 <b>Сторінка {page+1}</b>:", parse_mode="HTML", reply_markup=category_page_kb(cats, page, total, group))
    await cb.answer()

@router.callback_query(F.data == "change_cat")
async def cb_change_cat(cb: CallbackQuery):
    await cb.message.edit_text("😆 Обери розділ у меню нижче 👇")
    await cb.answer()

# === CATEGORY → PRANK LIST ===
@router.callback_query(F.data.startswith("cat_"))
async def cb_open_cat(cb: CallbackQuery):
    cat_id = int(cb.data.split("_")[1])
    rows = await get_pranks_in_cat(cat_id)
    if not rows:
        return await cb.answer("📭 У цій категорії поки немає аудіо.", show_alert=True)
    p = rows[0]
    text = f"🎵 <b>{p[1]}</b>\n📂 Категорія #{cat_id}\n▶ {p[2]} прослуховувань"
    await cb.message.edit_text(text, parse_mode="HTML", reply_markup=prank_card_kb(p[0], cat_id, 0, len(rows)))
    await cb.answer()

@router.callback_query(F.data.startswith("pnav_"))
async def cb_prank_nav(cb: CallbackQuery):
    parts = cb.data.split("_")
    cat_id = int(parts[1])
    index = int(parts[2])
    rows = await get_pranks_in_cat(cat_id)
    if index >= len(rows): index = len(rows)-1
    p = rows[index]
    text = f"🎵 <b>{p[1]}</b>\n📂 Категорія #{cat_id}\n▶ {p[2]} прослуховувань"
    await cb.message.edit_text(text, parse_mode="HTML", reply_markup=prank_card_kb(p[0], cat_id, index, len(rows)))
    await cb.answer()

@router.callback_query(F.data.startswith("play_"))
async def cb_play(cb: CallbackQuery):
    prank_id = int(cb.data.split("_")[1])
    db = await get_db()
    cur = await db.execute("SELECT file_id, title FROM pranks WHERE id=?", (prank_id,))
    row = await cur.fetchone()
    if row:
        await db.execute("UPDATE pranks SET play_count=play_count+1 WHERE id=?", (prank_id,))
        await db.commit()
        await cb.message.answer_audio(row[0], caption=f"🎵 <b>{row[1]}</b>", parse_mode="HTML")
    await db.close()
    await cb.answer("▶ Відтворення...")

@router.callback_query(F.data.startswith("fav_"))
async def cb_fav(cb: CallbackQuery):
    prank_id = int(cb.data.split("_")[1])
    db = await get_db()
    try:
        await db.execute("INSERT INTO favorites (user_id, prank_id) VALUES (?,?)", (cb.from_user.id, prank_id))
        await db.commit()
        await cb.answer("❤️ Додано в обране!", show_alert=True)
    except:
        await cb.answer("Вже в обраному!", show_alert=True)
    await db.close()

@router.callback_query(F.data.startswith("backcat_"))
async def cb_back_cat(cb: CallbackQuery):
    cat_id = int(cb.data.split("_")[1])
    db = await get_db()
    cur = await db.execute("SELECT group_name, page_num FROM categories WHERE id=?", (cat_id,))
    row = await cur.fetchone()
    await db.close()
    group = row[0] if row else "categories"
    page = row[1] if row else 0
    cats, total = await get_page_cats(group, page)
    await cb.message.edit_text(f"📝 <b>Сторінка {page+1}</b>:", parse_mode="HTML", reply_markup=category_page_kb(cats, page, total, group))
    await cb.answer()

# === ADMIN PANEL ===
@router.message(Command("admin"))
async def cmd_admin(msg: Message):
    if msg.from_user.id not in ADMIN_IDS: return
    db = await get_db()
    u = (await (await db.execute("SELECT COUNT(*) FROM users")).fetchone())[0]
    p = (await (await db.execute("SELECT COUNT(*) FROM pranks")).fetchone())[0]
    plays = (await (await db.execute("SELECT SUM(play_count) FROM pranks")).fetchone())[0] or 0
    await db.close()
    await msg.answer(
        f"🔧 <b>Адмін-панель</b>\n\n"
        f"👥 Користувачів: {u}\n"
        f"🎵 Аудіо: {p}\n"
        f"▶ Прослуховувань: {plays}\n\n"
        f"📤 Надішліть аудіо — крок за кроком збережемо\n"
        f"/manage — Керування записами\n"
        f"/broadcast Текст — розсилка\n"
        f"/delaudio ID — видалити\n"
        f"/listaudio ID_категорії — список", parse_mode="HTML"
    )

@router.message(F.audio | F.voice, F.from_user.id.in_(ADMIN_IDS))
async def admin_audio(msg: Message, state: FSMContext):
    audio = msg.audio or msg.voice
    file_id = audio.file_id
    # Store file_id in FSM and ask for title
    await state.set_state(AddAudio.waiting_title)
    await state.update_data(file_id=file_id)
    await msg.answer("📝 <b>Введіть назву запису:</b>\n\n<i>Наприклад: Гурген хоче познайомитися</i>", parse_mode="HTML")

@router.message(AddAudio.waiting_title)
async def admin_title_entered(msg: Message, state: FSMContext):
    if msg.from_user.id not in ADMIN_IDS:
        await state.clear()
        return
    title = msg.text.strip()
    if not title:
        return await msg.answer("❌ Назва не може бути порожньою. Спробуйте ще раз:")
    await state.update_data(title=title)
    await state.set_state(AddAudio.waiting_category)
    # Show categories
    db = await get_db()
    cur = await db.execute("SELECT id, name FROM categories ORDER BY group_name, page_num, sort_order")
    rows = await cur.fetchall()
    await db.close()
    buttons = [[InlineKeyboardButton(text=r[1], callback_data=f"fsm_cat_{r[0]}")] for r in rows[:30]]
    buttons.append([InlineKeyboardButton(text="❌ Скасувати", callback_data="fsm_cancel")])
    await msg.answer(f"📂 <b>Оберіть категорію для:</b>\n🎵 {title}", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@router.callback_query(F.data.startswith("fsm_cat_"))
async def admin_fsm_cat_selected(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id not in ADMIN_IDS:
        return await cb.answer("❌")
    cat_id = int(cb.data.split("_")[2])
    data = await state.get_data()
    if not data.get("file_id"):
        await state.clear()
        return await cb.answer("❌ Сесія закінчилась")
    # Save to DB
    db = await get_db()
    await db.execute("INSERT INTO pranks (title, file_id, category_id) VALUES (?,?,?)", (data["title"], data["file_id"], cat_id))
    await db.commit()
    cur = await db.execute("SELECT name FROM categories WHERE id=?", (cat_id,))
    cat_name = (await cur.fetchone())[0]
    await db.close()
    await state.clear()
    await cb.message.edit_text(f"✅ <b>Запис збережено!</b>\n\n🎵 {data['title']}\n📂 {cat_name}", parse_mode="HTML")
    await cb.answer("✅ Збережено!")

@router.callback_query(F.data == "fsm_cancel")
async def admin_fsm_cancel(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text("❌ Скасовано")
    await cb.answer()

# === ADMIN: MANAGE RECORDINGS ===
@router.message(Command("manage"))
async def cmd_manage(msg: Message):
    if msg.from_user.id not in ADMIN_IDS: return
    db = await get_db()
    cur = await db.execute("SELECT id, title, category_id FROM pranks ORDER BY id DESC LIMIT 10")
    rows = await cur.fetchall()
    await db.close()
    if not rows:
        return await msg.answer("📭 Немає записів")
    buttons = [[InlineKeyboardButton(text=f"🎵 {r[1]}", callback_data=f"mgr_{r[0]}")] for r in rows]
    buttons.append([InlineKeyboardButton(text="📄 Далі →", callback_data="mgr_page_1")])
    await msg.answer("⚙️ <b>Керування записами:</b>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@router.callback_query(F.data.startswith("mgr_page_"))
async def cb_mgr_page(cb: CallbackQuery):
    if cb.from_user.id not in ADMIN_IDS: return await cb.answer("❌")
    page = int(cb.data.split("_")[2])
    offset = page * 10
    db = await get_db()
    cur = await db.execute("SELECT id, title FROM pranks ORDER BY id DESC LIMIT 10 OFFSET ?", (offset,))
    rows = await cur.fetchall()
    await db.close()
    if not rows:
        return await cb.answer("Більше немає записів")
    buttons = [[InlineKeyboardButton(text=f"🎵 {r[1]}", callback_data=f"mgr_{r[0]}")] for r in rows]
    nav = []
    if page > 0: nav.append(InlineKeyboardButton(text="← Назад", callback_data=f"mgr_page_{page-1}"))
    nav.append(InlineKeyboardButton(text="Далі →", callback_data=f"mgr_page_{page+1}"))
    buttons.append(nav)
    await cb.message.edit_text("⚙️ <b>Керування записами:</b>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()

@router.callback_query(F.data.regexp(r"^mgr_\d+$"))
async def cb_mgr_detail(cb: CallbackQuery):
    if cb.from_user.id not in ADMIN_IDS: return await cb.answer("❌")
    prank_id = int(cb.data.split("_")[1])
    db = await get_db()
    cur = await db.execute("SELECT id, title, play_count, category_id FROM pranks WHERE id=?", (prank_id,))
    row = await cur.fetchone()
    cat = await db.execute("SELECT name FROM categories WHERE id=?", (row[3],))
    cat_name = (await cat.fetchone())[0] if row[3] else "?"
    await db.close()
    buttons = [
        [InlineKeyboardButton(text="▶ Прослухати", callback_data=f"mplay_{prank_id}")],
        [InlineKeyboardButton(text="✏️ Перейменувати", callback_data=f"mren_{prank_id}"),
         InlineKeyboardButton(text="📂 Змінити категорію", callback_data=f"mchcat_{prank_id}")],
        [InlineKeyboardButton(text="🗑 Видалити", callback_data=f"mdel_{prank_id}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="mgr_page_0")],
    ]
    await cb.message.edit_text(
        f"🎵 <b>{row[1]}</b>\n📂 {cat_name}\n▶ {row[2]} прослуховувань\n🆔 #{row[0]}",
        parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await cb.answer()

@router.callback_query(F.data.startswith("mplay_"))
async def cb_mgr_play(cb: CallbackQuery):
    prank_id = int(cb.data.split("_")[1])
    db = await get_db()
    cur = await db.execute("SELECT file_id, title FROM pranks WHERE id=?", (prank_id,))
    row = await cur.fetchone()
    await db.close()
    if row:
        await cb.message.answer_audio(row[0], caption=f"🎵 {row[1]}")
    await cb.answer()

@router.callback_query(F.data.startswith("mren_"))
async def cb_mgr_rename(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id not in ADMIN_IDS: return await cb.answer("❌")
    prank_id = int(cb.data.split("_")[1])
    await state.set_state(RenameAudio.waiting_new_title)
    await state.update_data(rename_id=prank_id)
    await cb.message.edit_text("✏️ <b>Введіть нову назву:</b>", parse_mode="HTML")
    await cb.answer()

@router.message(RenameAudio.waiting_new_title)
async def admin_rename_done(msg: Message, state: FSMContext):
    if msg.from_user.id not in ADMIN_IDS:
        await state.clear()
        return
    data = await state.get_data()
    new_title = msg.text.strip()
    if not new_title:
        return await msg.answer("❌ Назва не може бути порожньою")
    db = await get_db()
    await db.execute("UPDATE pranks SET title=?, updated_at=datetime('now') WHERE id=?", (new_title, data["rename_id"]))
    await db.commit()
    await db.close()
    await state.clear()
    await msg.answer(f"✅ Перейменовано на: <b>{new_title}</b>", parse_mode="HTML")

@router.callback_query(F.data.startswith("mdel_"))
async def cb_mgr_delete_confirm(cb: CallbackQuery):
    if cb.from_user.id not in ADMIN_IDS: return await cb.answer("❌")
    prank_id = int(cb.data.split("_")[1])
    buttons = [
        [InlineKeyboardButton(text="✅ Так, видалити", callback_data=f"mdelyes_{prank_id}"),
         InlineKeyboardButton(text="❌ Ні", callback_data="mgr_page_0")]
    ]
    await cb.message.edit_text("🗑 <b>Ви впевнені що хочете видалити?</b>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()

@router.callback_query(F.data.startswith("mdelyes_"))
async def cb_mgr_delete_yes(cb: CallbackQuery):
    if cb.from_user.id not in ADMIN_IDS: return await cb.answer("❌")
    prank_id = int(cb.data.split("_")[1])
    db = await get_db()
    await db.execute("DELETE FROM favorites WHERE prank_id=?", (prank_id,))
    await db.execute("DELETE FROM pranks WHERE id=?", (prank_id,))
    await db.commit()
    await db.close()
    await cb.message.edit_text("✅ Запис видалено!")
    await cb.answer("Видалено")

@router.callback_query(F.data.startswith("mchcat_"))
async def cb_mgr_change_cat(cb: CallbackQuery):
    if cb.from_user.id not in ADMIN_IDS: return await cb.answer("❌")
    prank_id = int(cb.data.split("_")[1])
    db = await get_db()
    cur = await db.execute("SELECT id, name FROM categories ORDER BY group_name, page_num, sort_order")
    rows = await cur.fetchall()
    await db.close()
    buttons = [[InlineKeyboardButton(text=r[1], callback_data=f"msetcat_{prank_id}_{r[0]}")] for r in rows[:30]]
    await cb.message.edit_text("📂 <b>Оберіть нову категорію:</b>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()

@router.callback_query(F.data.startswith("msetcat_"))
async def cb_mgr_set_cat(cb: CallbackQuery):
    if cb.from_user.id not in ADMIN_IDS: return await cb.answer("❌")
    parts = cb.data.split("_")
    prank_id = int(parts[1])
    cat_id = int(parts[2])
    db = await get_db()
    await db.execute("UPDATE pranks SET category_id=?, updated_at=datetime('now') WHERE id=?", (cat_id, prank_id))
    await db.commit()
    cur = await db.execute("SELECT name FROM categories WHERE id=?", (cat_id,))
    cat_name = (await cur.fetchone())[0]
    await db.close()
    await cb.message.edit_text(f"✅ Категорію змінено на: <b>{cat_name}</b>", parse_mode="HTML")
    await cb.answer("✅")

@router.message(Command("broadcast"))
async def cmd_broadcast(msg: Message):
    if msg.from_user.id not in ADMIN_IDS: return
    text = msg.text.replace("/broadcast","").strip()
    if not text: return await msg.answer("Формат: /broadcast Текст")
    db = await get_db()
    cur = await db.execute("SELECT telegram_id FROM users")
    rows = await cur.fetchall()
    await db.close()
    sent = 0
    for r in rows:
        try: await bot.send_message(r[0], text); sent+=1
        except: pass
    await msg.answer(f"✅ Розіслано {sent}/{len(rows)}")

@router.message(Command("delaudio"))
async def cmd_delaudio(msg: Message):
    if msg.from_user.id not in ADMIN_IDS: return
    try:
        aid = int(msg.text.split()[1])
        db = await get_db()
        await db.execute("DELETE FROM pranks WHERE id=?", (aid,))
        await db.commit(); await db.close()
        await msg.answer(f"✅ Видалено #{aid}")
    except: await msg.answer("Формат: /delaudio ID")

@router.message(Command("listaudio"))
async def cmd_listaudio(msg: Message):
    if msg.from_user.id not in ADMIN_IDS: return
    try:
        cid = int(msg.text.split()[1])
        db = await get_db()
        cur = await db.execute("SELECT id, title, play_count FROM pranks WHERE category_id=? ORDER BY id", (cid,))
        rows = await cur.fetchall(); await db.close()
        if not rows: return await msg.answer("Порожня категорія")
        text = "\n".join(f"#{r[0]} — {r[1]} (▶{r[2]})" for r in rows[:30])
        await msg.answer(f"📂 Аудіо в категорії #{cid}:\n\n{text}")
    except: await msg.answer("Формат: /listaudio ID_категорії")

# === SETUP ===
async def main():
    await init_db()
    await bot.set_my_commands([
        BotCommand(command="start", description="Запустити бота"),
        BotCommand(command="profile", description="Мій акаунт"),
        BotCommand(command="faq", description="FAQ"),
        BotCommand(command="top10", description="ТОП 10"),
        BotCommand(command="ref", description="Реферальне посилання"),
        BotCommand(command="pay", description="Поповнити баланс"),
        BotCommand(command="cancel", description="Скасувати"),
    ])
    logging.info("🤖 PrankBox запущено!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
