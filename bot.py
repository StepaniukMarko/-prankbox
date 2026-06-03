import asyncio
import logging
from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import Message, CallbackQuery, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN, ADMIN_IDS, REFERRAL_BONUS, SUPPORT_USERNAME
from database import (
    init_db, ensure_user, get_user, get_page_categories, get_all_categories,
    get_pranks_by_category, get_pranks_by_category_page, get_prank,
    get_top_pranks, get_random_pranks,
    increment_play_count, add_prank, delete_prank, rename_prank,
    change_prank_category, add_favorite, get_favorites, get_favorites_count,
    get_bot_stats, get_all_users_ids, get_pranks_paginated, get_category_name,
    get_category_info
)
from keyboards import (
    main_menu, pranks_menu, category_page_kb, prank_list_kb, prank_audio_kb,
    top_prank_kb, favorites_empty_kb, about_kb
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)

# Admin audio buffer: {user_id: {"items": [(file_id, title), ...], "task": asyncio.Task | None}}
admin_audio_buffer: dict = {}
BUFFER_DELAY = 2.0  # seconds to wait for more audio before showing category menu


# ═══════════════════════════════════════════════════════════════════
# FSM STATES
# ═══════════════════════════════════════════════════════════════════

class AddAudio(StatesGroup):
    waiting_category = State()


class RenameAudio(StatesGroup):
    waiting_new_title = State()


# ═══════════════════════════════════════════════════════════════════
# START & MAIN COMMANDS
# ═══════════════════════════════════════════════════════════════════

@router.message(Command("start"))
async def cmd_start(msg: Message):
    ref_id = None
    if msg.text and "ref_" in msg.text:
        try:
            ref_id = int(msg.text.split("ref_")[1])
        except (ValueError, IndexError):
            pass

    await ensure_user(msg.from_user.id, msg.from_user.username, msg.from_user.first_name, ref_id)

    await msg.answer(
        "🤪 <b>Ласкаво просимо до PrankBox!</b>\n\n"
        "🎧 Сотні аудіо для розіграшів друзів\n\n"
        "Обирай категорію та надсилай\n"
        "найсмішніші пранки 😆",
        parse_mode="HTML",
        reply_markup=main_menu()
    )


@router.message(Command("cancel"))
async def cmd_cancel(msg: Message, state: FSMContext):
    await state.clear()
    await msg.answer("❌ Скасовано", reply_markup=main_menu())


# ═══════════════════════════════════════════════════════════════════
# PROFILE
# ═══════════════════════════════════════════════════════════════════

@router.message(Command("profile"))
@router.message(F.text == "👤 Мій акаунт")
async def cmd_profile(msg: Message):
    await ensure_user(msg.from_user.id, msg.from_user.username, msg.from_user.first_name)
    user = await get_user(msg.from_user.id)
    fav_count = await get_favorites_count(msg.from_user.id)

    created = user["created_at"].strftime("%d.%m.%Y") if user["created_at"] else "—"

    await msg.answer(
        f"👤 <b>Мій акаунт</b>\n\n"
        f"┌ 🆔 ID: <code>{user['telegram_id']}</code>\n"
        f"├ 👤 Username: @{user['username'] or 'не вказано'}\n"
        f"├ 📅 Реєстрація: {created}\n"
        f"├ 💰 Баланс: {user['balance']} монет\n"
        f"├ 👥 Рефералів: {user['referral_count']}\n"
        f"└ ❤️ Обране: {fav_count}",
        parse_mode="HTML"
    )


# ═══════════════════════════════════════════════════════════════════
# TOP 10
# ═══════════════════════════════════════════════════════════════════

@router.message(Command("top10"))
@router.message(F.text == "🏆 ТОП 10")
async def cmd_top10(msg: Message):
    rows = await get_top_pranks(10)

    if not rows:
        return await msg.answer(
            "🏆 <b>Найпопулярніші аудіо сьогодні</b>\n\n"
            "📭 Поки що немає прослуховувань.\n"
            "Будь першим — слухай та діли з друзями!",
            parse_mode="HTML"
        )

    text = "🏆 <b>Найпопулярніші аудіо сьогодні</b>\n\n"
    medals = ["🥇", "🥈", "🥉"]

    for i, r in enumerate(rows):
        medal = medals[i] if i < 3 else f"  {i+1}."
        text += f"{medal} <b>{r['title']}</b>\n     🎧 {r['play_count']} прослуховувань\n\n"

    await msg.answer(text, parse_mode="HTML")


# ═══════════════════════════════════════════════════════════════════
# EARN (REFERRALS)
# ═══════════════════════════════════════════════════════════════════

@router.message(Command("ref"))
@router.message(F.text == "💸 Заробити")
async def cmd_earn(msg: Message):
    await ensure_user(msg.from_user.id, msg.from_user.username, msg.from_user.first_name)
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start=ref_{msg.from_user.id}"
    user = await get_user(msg.from_user.id)

    share_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Поділитися ботом", url=f"https://t.me/share/url?url={link}&text=🤪 PrankBox — аудіо для розіграшів друзів!")]
    ])

    await msg.answer(
        f"💰 <b>Отримуй монети за друзів</b>\n\n"
        f"👥 +{REFERRAL_BONUS} монет за кожного запрошеного\n\n"
        f"🔗 Твоє посилання:\n<code>{link}</code>\n\n"
        f"┌ 👥 Запрошено: {user['referral_count']}\n"
        f"└ 💰 Баланс: {user['balance']} монет\n\n"
        f"📤 Надішли посилання друзям!",
        parse_mode="HTML",
        reply_markup=share_kb
    )


# ═══════════════════════════════════════════════════════════════════
# STATISTICS
# ═══════════════════════════════════════════════════════════════════

@router.message(F.text == "📊 Статистика")
async def cmd_stats(msg: Message):
    stats = await get_bot_stats()
    await msg.answer(
        "📊 <b>Статистика бота</b>\n\n"
        f"┌ 🎵 Всього аудіо: {stats['pranks']}\n"
        f"├ 👥 Користувачів: {stats['users']}\n"
        f"├ 🎧 Прослуховувань: {stats['plays']}\n"
        f"└ 📂 Категорій: {stats['categories']}",
        parse_mode="HTML"
    )


@router.callback_query(F.data == "show_stats")
async def cb_show_stats(cb: CallbackQuery):
    stats = await get_bot_stats()
    await cb.message.edit_text(
        "📊 <b>Статистика бота</b>\n\n"
        f"┌ 🎵 Всього аудіо: {stats['pranks']}\n"
        f"├ 👥 Користувачів: {stats['users']}\n"
        f"├ 🎧 Прослуховувань: {stats['plays']}\n"
        f"└ 📂 Категорій: {stats['categories']}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="show_about")]
        ])
    )
    await cb.answer()


# ═══════════════════════════════════════════════════════════════════
# ABOUT BOT
# ═══════════════════════════════════════════════════════════════════

@router.message(F.text == "ℹ️ Про бота")
async def cmd_about(msg: Message):
    stats = await get_bot_stats()
    await msg.answer(
        "🤪 <b>PrankBox</b>\n\n"
        "🎧 Аудіо для розіграшів друзів\n\n"
        f"📊 <b>Статистика:</b>\n"
        f"┌ 🎵 Аудіо: {stats['pranks']}\n"
        f"├ 👥 Користувачів: {stats['users']}\n"
        f"└ 🎧 Прослуховувань: {stats['plays']}\n\n"
        f"👨‍💻 <b>Підтримка:</b> {SUPPORT_USERNAME}",
        parse_mode="HTML",
        reply_markup=about_kb()
    )


@router.callback_query(F.data == "show_about")
async def cb_show_about(cb: CallbackQuery):
    stats = await get_bot_stats()
    await cb.message.edit_text(
        "🤪 <b>PrankBox</b>\n\n"
        "🎧 Аудіо для розіграшів друзів\n\n"
        f"📊 <b>Статистика:</b>\n"
        f"┌ 🎵 Аудіо: {stats['pranks']}\n"
        f"├ 👥 Користувачів: {stats['users']}\n"
        f"└ 🎧 Прослуховувань: {stats['plays']}\n\n"
        f"👨‍💻 <b>Підтримка:</b> {SUPPORT_USERNAME}",
        parse_mode="HTML",
        reply_markup=about_kb()
    )
    await cb.answer()


# ═══════════════════════════════════════════════════════════════════
# FAQ
# ═══════════════════════════════════════════════════════════════════

@router.message(Command("faq"))
@router.message(F.text == "❓ FAQ")
async def cmd_faq(msg: Message):
    await msg.answer(
        "❓ <b>Часті запитання</b>\n\n"
        "🎵 <b>Як слухати?</b>\n"
        "    Обери категорію → натисни ▶️ Слухати\n\n"
        "❤️ <b>Як зберегти?</b>\n"
        "    Натисни ❤️ під аудіо\n\n"
        "💸 <b>Як заробити?</b>\n"
        "    Запрошуй друзів і отримуй монети\n\n"
        "📤 <b>Як надіслати?</b>\n"
        "    Натисни 📤 Надіслати під аудіо\n\n"
        f"📞 <b>Підтримка:</b> {SUPPORT_USERNAME}",
        parse_mode="HTML"
    )


@router.callback_query(F.data == "show_faq")
async def cb_show_faq(cb: CallbackQuery):
    await cb.message.edit_text(
        "❓ <b>Часті запитання</b>\n\n"
        "🎵 <b>Як слухати?</b>\n"
        "    Обери категорію → натисни ▶️ Слухати\n\n"
        "❤️ <b>Як зберегти?</b>\n"
        "    Натисни ❤️ під аудіо\n\n"
        "💸 <b>Як заробити?</b>\n"
        "    Запрошуй друзів і отримуй монети\n\n"
        "📤 <b>Як надіслати?</b>\n"
        "    Натисни 📤 Надіслати під аудіо\n\n"
        f"📞 <b>Підтримка:</b> {SUPPORT_USERNAME}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="show_about")]
        ])
    )
    await cb.answer()


# ═══════════════════════════════════════════════════════════════════
# PRANKS NAVIGATION
# ═══════════════════════════════════════════════════════════════════

@router.message(F.text == "😆 Розіграші")
async def menu_pranks(msg: Message):
    await msg.answer("😆 <b>Обери розділ:</b>", parse_mode="HTML", reply_markup=pranks_menu())


@router.message(F.text == "🏁 Головне меню")
async def menu_main(msg: Message):
    await msg.answer("🏠 <b>Головне меню</b>", parse_mode="HTML", reply_markup=main_menu())


@router.message(F.text == "📝 Категорії")
async def menu_cats(msg: Message):
    cats, total = await get_page_categories("categories", 0)
    if not cats:
        return await msg.answer("📭 Категорії поки що порожні")
    await msg.answer(
        "📝 <b>Категорії</b>",
        parse_mode="HTML",
        reply_markup=category_page_kb(cats, 0, total, "categories")
    )


@router.message(F.text == "👦👩 Іменні")
async def menu_named(msg: Message):
    cats, total = await get_page_categories("named", 0)
    if not cats:
        return await msg.answer("📭 Поки немає іменних записів")
    await msg.answer(
        "👦👩 <b>Іменні розіграші</b>",
        parse_mode="HTML",
        reply_markup=category_page_kb(cats, 0, total, "named")
    )


@router.message(F.text == "🎉 Свята")
async def menu_holidays(msg: Message):
    cats, total = await get_page_categories("holidays", 0)
    if not cats:
        return await msg.answer("📭 Поки немає святкових записів")
    await msg.answer(
        "🎉 <b>Святкові розіграші</b>",
        parse_mode="HTML",
        reply_markup=category_page_kb(cats, 0, total, "holidays")
    )


# ═══════════════════════════════════════════════════════════════════
# RANDOM PRANKS
# ═══════════════════════════════════════════════════════════════════

@router.message(F.text == "🌀 Випадкові")
async def menu_random(msg: Message):
    rows = await get_random_pranks(3)
    if not rows:
        return await msg.answer("📭 Поки що немає аудіо.")

    await msg.answer("🌀 <b>Випадкові записи:</b>", parse_mode="HTML")
    for r in rows:
        await msg.answer_audio(
            r["file_id"],
            caption=f"🎵 <b>{r['title']}</b>\n🎧 {r['play_count']} прослуховувань",
            parse_mode="HTML",
            reply_markup=prank_audio_kb(r['id'])
        )


# ═══════════════════════════════════════════════════════════════════
# FAVORITES
# ═══════════════════════════════════════════════════════════════════

@router.message(F.text == "❤️ Обране")
async def menu_fav(msg: Message):
    rows = await get_favorites(msg.from_user.id)

    if not rows:
        return await msg.answer(
            "❤️ <b>Тут поки немає обраних</b>\n\n"
            "Натискай ❤️ під аудіо щоб зберігати їх",
            parse_mode="HTML",
            reply_markup=favorites_empty_kb()
        )

    await msg.answer(f"❤️ <b>Обране</b> ({len(rows)} аудіо):", parse_mode="HTML")
    for r in rows[:10]:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="📢 Поділитися", callback_data=f"share_{r['id']}"),
            ]
        ])
        await msg.answer_audio(
            r["file_id"],
            caption=f"❤️ <b>{r['title']}</b>\n🎧 {r['play_count']} прослуховувань",
            parse_mode="HTML",
            reply_markup=kb
        )


@router.callback_query(F.data == "go_pranks")
async def cb_go_pranks(cb: CallbackQuery):
    await cb.message.answer("😆 <b>Обери розділ:</b>", parse_mode="HTML", reply_markup=pranks_menu())
    await cb.answer()


# ═══════════════════════════════════════════════════════════════════
# PAGINATION CALLBACKS
# ═══════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("pg_"))
async def cb_page(cb: CallbackQuery):
    parts = cb.data.split("_")
    group = parts[1]
    page = int(parts[2])
    cats, total = await get_page_categories(group, page)

    if not cats:
        return await cb.answer("Немає більше сторінок")

    titles = {"categories": "📝 Категорії", "named": "👦👩 Іменні", "holidays": "🎉 Свята"}
    title = titles.get(group, "📝 Категорії")

    await cb.message.edit_text(
        f"{title} <b>(стор. {page+1})</b>",
        parse_mode="HTML",
        reply_markup=category_page_kb(cats, page, total, group)
    )
    await cb.answer()


@router.callback_query(F.data == "change_cat")
async def cb_change_cat(cb: CallbackQuery):
    await cb.message.answer("😆 <b>Обери розділ:</b>", parse_mode="HTML", reply_markup=pranks_menu())
    await cb.answer()


@router.callback_query(F.data == "noop")
async def cb_noop(cb: CallbackQuery):
    await cb.answer()


# ═══════════════════════════════════════════════════════════════════
# CATEGORY → PRANK LIST (shows all at once, paginated by 10)
# ═══════════════════════════════════════════════════════════════════

PRANKS_PER_PAGE = 10


@router.callback_query(F.data.startswith("cat_"))
async def cb_open_cat(cb: CallbackQuery):
    cat_id = int(cb.data.split("_")[1])
    rows, total = await get_pranks_by_category_page(cat_id, 0, PRANKS_PER_PAGE)

    if not rows:
        return await cb.answer("📭 У цій категорії поки немає аудіо", show_alert=True)

    cat_name = await get_category_name(cat_id)
    text = f"📂 <b>{cat_name}</b> — {total} аудіо\n\nНатисни ▶️ щоб прослухати:"

    await cb.message.edit_text(
        text, parse_mode="HTML",
        reply_markup=prank_list_kb(rows, cat_id, 0, total, PRANKS_PER_PAGE)
    )
    await cb.answer()


@router.callback_query(F.data.startswith("clist_"))
async def cb_cat_list_page(cb: CallbackQuery):
    """Pagination within a category prank list."""
    parts = cb.data.split("_")
    cat_id = int(parts[1])
    page = int(parts[2])
    offset = page * PRANKS_PER_PAGE

    rows, total = await get_pranks_by_category_page(cat_id, offset, PRANKS_PER_PAGE)
    if not rows:
        return await cb.answer("Немає більше аудіо")

    cat_name = await get_category_name(cat_id)
    text = f"📂 <b>{cat_name}</b> — {total} аудіо\n\nНатисни ▶️ щоб прослухати:"

    await cb.message.edit_text(
        text, parse_mode="HTML",
        reply_markup=prank_list_kb(rows, cat_id, page, total, PRANKS_PER_PAGE)
    )
    await cb.answer()


# ═══════════════════════════════════════════════════════════════════
# PLAY, FAVORITE & SHARE
# ═══════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("play_"))
async def cb_play(cb: CallbackQuery):
    prank_id = int(cb.data.split("_")[1])
    row = await increment_play_count(prank_id)

    if row:
        await cb.message.answer_audio(
            row["file_id"],
            caption=f"🎵 <b>{row['title']}</b>\n🎧 {row['play_count']} прослуховувань",
            parse_mode="HTML",
            reply_markup=prank_audio_kb(prank_id)
        )
    await cb.answer("▶️ Відтворення")


@router.callback_query(F.data.startswith("share_"))
async def cb_share(cb: CallbackQuery):
    """Share bot link with referral."""
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start=ref_{cb.from_user.id}"
    await cb.message.answer(
        "🤪 <b>Поділися PrankBox з друзями!</b>\n\n"
        "🎧 Сотні аудіо для розіграшів\n\n"
        f"🔗 Твоє посилання:\n<code>{link}</code>\n\n"
        "👥 Запрошуй друзів та отримуй монети",
        parse_mode="HTML"
    )
    await cb.answer()


@router.callback_query(F.data.startswith("fav_"))
async def cb_fav(cb: CallbackQuery):
    prank_id = int(cb.data.split("_")[1])
    added = await add_favorite(cb.from_user.id, prank_id)

    if added:
        await cb.answer("❤️ Додано в обране!", show_alert=True)
    else:
        await cb.answer("Вже в обраному!", show_alert=True)


@router.callback_query(F.data.startswith("backcat_"))
async def cb_back_cat(cb: CallbackQuery):
    cat_id = int(cb.data.split("_")[1])
    info = await get_category_info(cat_id)
    group = info["group_name"] if info else "categories"
    page = info["page_num"] if info else 0

    cats, total = await get_page_categories(group, page)
    titles = {"categories": "📝 Категорії", "named": "👦👩 Іменні", "holidays": "🎉 Свята"}
    title = titles.get(group, "📝 Категорії")

    await cb.message.edit_text(
        f"{title} <b>(стор. {page+1})</b>",
        parse_mode="HTML",
        reply_markup=category_page_kb(cats, page, total, group)
    )
    await cb.answer()


# ═══════════════════════════════════════════════════════════════════
# ADMIN PANEL
# ═══════════════════════════════════════════════════════════════════

@router.message(Command("admin"))
async def cmd_admin(msg: Message):
    if msg.from_user.id not in ADMIN_IDS:
        return

    stats = await get_bot_stats()
    await msg.answer(
        "🔧 <b>Адмін-панель PrankBox</b>\n\n"
        f"┌ 👥 Користувачів: {stats['users']}\n"
        f"├ 🎵 Аудіо: {stats['pranks']}\n"
        f"├ 🎧 Прослуховувань: {stats['plays']}\n"
        f"└ 📂 Категорій: {stats['categories']}\n\n"
        "📤 Надішліть аудіо (можна декілька) — назва автоматична\n\n"
        "<b>Команди:</b>\n"
        "/manage — Керування записами\n"
        "/broadcast Текст — Розсилка\n"
        "/delaudio ID — Видалити запис\n"
        "/listaudio ID — Список аудіо в категорії",
        parse_mode="HTML"
    )


@router.message(F.audio | F.voice, F.from_user.id.in_(ADMIN_IDS))
async def admin_audio(msg: Message, state: FSMContext):
    audio = msg.audio or msg.voice
    file_id = audio.file_id

    # Auto-extract title: Telegram title > file_name (without extension) > fallback
    title = None
    if msg.audio:
        if msg.audio.title:
            title = msg.audio.title.strip()
        elif msg.audio.file_name:
            name = msg.audio.file_name
            if "." in name:
                title = name.rsplit(".", 1)[0].strip()
            else:
                title = name.strip()
    if not title:
        title = f"Аудіо #{msg.message_id}"

    user_id = msg.from_user.id

    # Add to buffer
    if user_id not in admin_audio_buffer:
        admin_audio_buffer[user_id] = {"items": [], "task": None}

    admin_audio_buffer[user_id]["items"].append((file_id, title))

    # Cancel previous debounce timer if exists
    if admin_audio_buffer[user_id]["task"] and not admin_audio_buffer[user_id]["task"].done():
        admin_audio_buffer[user_id]["task"].cancel()

    # Start new debounce timer
    async def show_category_menu():
        await asyncio.sleep(BUFFER_DELAY)
        items = admin_audio_buffer[user_id]["items"]
        if not items:
            return

        # Save items to FSM state for category selection
        await state.set_state(AddAudio.waiting_category)
        await state.update_data(batch_items=items)

        cats = await get_all_categories()
        buttons = [[InlineKeyboardButton(text=f"{c['emoji']} {c['name']}", callback_data=f"fsm_cat_{c['id']}")] for c in cats[:30]]
        buttons.append([InlineKeyboardButton(text="❌ Скасувати", callback_data="fsm_cancel")])

        count = len(items)
        if count == 1:
            text = f"📂 <b>Оберіть категорію для:</b>\n\n🎵 <b>{items[0][1]}</b>"
        else:
            titles_preview = "\n".join(f"  • {t}" for _, t in items[:5])
            extra = f"\n  ... та ще {count - 5}" if count > 5 else ""
            text = f"📂 <b>Оберіть категорію для {count} аудіо:</b>\n\n{titles_preview}{extra}"

        await msg.answer(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

        # Clear buffer after showing menu
        admin_audio_buffer[user_id]["items"] = []
        admin_audio_buffer[user_id]["task"] = None

    admin_audio_buffer[user_id]["task"] = asyncio.create_task(show_category_menu())


@router.callback_query(F.data.startswith("fsm_cat_"))
async def admin_fsm_cat_selected(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id not in ADMIN_IDS:
        return await cb.answer("❌")

    cat_id = int(cb.data.split("_")[2])
    data = await state.get_data()
    batch_items = data.get("batch_items", [])

    if not batch_items:
        await state.clear()
        return await cb.answer("❌ Сесія закінчилась")

    cat_name = await get_category_name(cat_id)
    added = 0
    skipped = 0

    for file_id, title in batch_items:
        prank_id = await add_prank(title, file_id, cat_id)
        if prank_id:
            added += 1
        else:
            skipped += 1

    await state.clear()

    # Build result message
    text = f"✅ <b>Додано {added} аудіо в категорію:</b>\n📂 {cat_name}"
    if skipped > 0:
        text += f"\n⚠️ Пропущено дублікатів: {skipped}"

    buttons = [
        [InlineKeyboardButton(text="📂 Вибрати іншу категорію", callback_data=f"fsm_recat_{cat_id}")],
    ]

    await cb.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer(f"✅ Додано {added}")


@router.callback_query(F.data.startswith("fsm_recat_"))
async def admin_fsm_recat(cb: CallbackQuery, state: FSMContext):
    """Show category menu again to move recently added audio to another category."""
    if cb.from_user.id not in ADMIN_IDS:
        return await cb.answer("❌")

    cats = await get_all_categories()
    buttons = [[InlineKeyboardButton(text=f"{c['emoji']} {c['name']}", callback_data=f"fsm_cat_{c['id']}")] for c in cats[:30]]
    buttons.append([InlineKeyboardButton(text="❌ Скасувати", callback_data="fsm_cancel")])

    # Check if we still have items in the user's buffer or need to get from DB
    await cb.message.edit_text(
        "📂 <b>Оберіть нову категорію:</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await cb.answer()


@router.callback_query(F.data == "fsm_cancel")
async def admin_fsm_cancel(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text("❌ Скасовано")
    await cb.answer()


# ═══════════════════════════════════════════════════════════════════
# ADMIN: MANAGE RECORDINGS
# ═══════════════════════════════════════════════════════════════════

@router.message(Command("manage"))
async def cmd_manage(msg: Message):
    if msg.from_user.id not in ADMIN_IDS:
        return

    rows = await get_pranks_paginated(0, 10)
    if not rows:
        return await msg.answer("📭 Немає записів")

    buttons = [[InlineKeyboardButton(text=f"🎵 {r['title']}", callback_data=f"mgr_{r['id']}")] for r in rows]
    buttons.append([InlineKeyboardButton(text="📄 Далі →", callback_data="mgr_page_1")])
    await msg.answer("⚙️ <b>Керування записами:</b>", parse_mode="HTML",
                     reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(F.data.startswith("mgr_page_"))
async def cb_mgr_page(cb: CallbackQuery):
    if cb.from_user.id not in ADMIN_IDS:
        return await cb.answer("❌")

    page = int(cb.data.split("_")[2])
    offset = page * 10
    rows = await get_pranks_paginated(offset, 10)

    if not rows:
        return await cb.answer("Більше немає записів")

    buttons = [[InlineKeyboardButton(text=f"🎵 {r['title']}", callback_data=f"mgr_{r['id']}")] for r in rows]
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="← Назад", callback_data=f"mgr_page_{page-1}"))
    nav.append(InlineKeyboardButton(text="Далі →", callback_data=f"mgr_page_{page+1}"))
    buttons.append(nav)

    await cb.message.edit_text("⚙️ <b>Керування записами:</b>", parse_mode="HTML",
                               reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()


@router.callback_query(F.data.regexp(r"^mgr_\d+$"))
async def cb_mgr_detail(cb: CallbackQuery):
    if cb.from_user.id not in ADMIN_IDS:
        return await cb.answer("❌")

    prank_id = int(cb.data.split("_")[1])
    prank = await get_prank(prank_id)
    if not prank:
        return await cb.answer("Запис не знайдено")

    cat_name = await get_category_name(prank["category_id"]) if prank["category_id"] else "—"

    buttons = [
        [InlineKeyboardButton(text="▶️ Прослухати", callback_data=f"mplay_{prank_id}")],
        [InlineKeyboardButton(text="✏️ Перейменувати", callback_data=f"mren_{prank_id}"),
         InlineKeyboardButton(text="📂 Змінити кат.", callback_data=f"mchcat_{prank_id}")],
        [InlineKeyboardButton(text="🗑 Видалити", callback_data=f"mdel_{prank_id}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="mgr_page_0")],
    ]
    await cb.message.edit_text(
        f"🎵 <b>{prank['title']}</b>\n\n"
        f"📂 {cat_name}\n"
        f"🎧 {prank['play_count']} прослуховувань\n"
        f"🆔 #{prank['id']}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await cb.answer()


@router.callback_query(F.data.startswith("mplay_"))
async def cb_mgr_play(cb: CallbackQuery):
    prank_id = int(cb.data.split("_")[1])
    prank = await get_prank(prank_id)
    if prank:
        await cb.message.answer_audio(prank["file_id"], caption=f"🎵 {prank['title']}")
    await cb.answer()


@router.callback_query(F.data.startswith("mren_"))
async def cb_mgr_rename(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id not in ADMIN_IDS:
        return await cb.answer("❌")

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
    new_title = msg.text.strip() if msg.text else ""
    if not new_title:
        return await msg.answer("❌ Назва не може бути порожньою")

    await rename_prank(data["rename_id"], new_title)
    await state.clear()
    await msg.answer(f"✅ Перейменовано: <b>{new_title}</b>", parse_mode="HTML")


@router.callback_query(F.data.startswith("mdel_"))
async def cb_mgr_delete_confirm(cb: CallbackQuery):
    if cb.from_user.id not in ADMIN_IDS:
        return await cb.answer("❌")

    prank_id = int(cb.data.split("_")[1])
    buttons = [
        [InlineKeyboardButton(text="✅ Так, видалити", callback_data=f"mdelyes_{prank_id}"),
         InlineKeyboardButton(text="❌ Ні", callback_data="mgr_page_0")]
    ]
    await cb.message.edit_text(
        "🗑 <b>Ви впевнені що хочете видалити?</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await cb.answer()


@router.callback_query(F.data.startswith("mdelyes_"))
async def cb_mgr_delete_yes(cb: CallbackQuery):
    if cb.from_user.id not in ADMIN_IDS:
        return await cb.answer("❌")

    prank_id = int(cb.data.split("_")[1])
    await delete_prank(prank_id)
    await cb.message.edit_text("✅ Запис видалено!")
    await cb.answer("Видалено")


@router.callback_query(F.data.startswith("mchcat_"))
async def cb_mgr_change_cat(cb: CallbackQuery):
    if cb.from_user.id not in ADMIN_IDS:
        return await cb.answer("❌")

    prank_id = int(cb.data.split("_")[1])
    cats = await get_all_categories()
    buttons = [[InlineKeyboardButton(text=f"{c['emoji']} {c['name']}", callback_data=f"msetcat_{prank_id}_{c['id']}")] for c in cats[:30]]
    buttons.append([InlineKeyboardButton(text="❌ Скасувати", callback_data="mgr_page_0")])

    await cb.message.edit_text(
        "📂 <b>Оберіть нову категорію:</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await cb.answer()


@router.callback_query(F.data.startswith("msetcat_"))
async def cb_mgr_set_cat(cb: CallbackQuery):
    if cb.from_user.id not in ADMIN_IDS:
        return await cb.answer("❌")

    parts = cb.data.split("_")
    prank_id = int(parts[1])
    cat_id = int(parts[2])

    await change_prank_category(prank_id, cat_id)
    cat_name = await get_category_name(cat_id)
    await cb.message.edit_text(f"✅ Категорію змінено: <b>{cat_name}</b>", parse_mode="HTML")
    await cb.answer("✅")


# ═══════════════════════════════════════════════════════════════════
# ADMIN: BROADCAST & UTILS
# ═══════════════════════════════════════════════════════════════════

@router.message(Command("broadcast"))
async def cmd_broadcast(msg: Message):
    if msg.from_user.id not in ADMIN_IDS:
        return

    text = msg.text.replace("/broadcast", "").strip()
    if not text:
        return await msg.answer("📝 Формат: /broadcast Текст повідомлення")

    user_ids = await get_all_users_ids()
    sent = 0
    for uid in user_ids:
        try:
            await bot.send_message(uid, text, parse_mode="HTML")
            sent += 1
        except Exception:
            pass

    await msg.answer(f"✅ Розіслано: {sent}/{len(user_ids)}")


@router.message(Command("delaudio"))
async def cmd_delaudio(msg: Message):
    if msg.from_user.id not in ADMIN_IDS:
        return
    try:
        aid = int(msg.text.split()[1])
        await delete_prank(aid)
        await msg.answer(f"✅ Видалено #{aid}")
    except (IndexError, ValueError):
        await msg.answer("📝 Формат: /delaudio ID")


@router.message(Command("listaudio"))
async def cmd_listaudio(msg: Message):
    if msg.from_user.id not in ADMIN_IDS:
        return
    try:
        cid = int(msg.text.split()[1])
        rows = await get_pranks_by_category(cid)
        if not rows:
            return await msg.answer("📭 Порожня категорія")
        cat_name = await get_category_name(cid)
        text = f"📂 <b>{cat_name}</b>:\n\n"
        text += "\n".join(f"#{r[0]} — {r[1]} (🎧 {r[2]})" for r in rows[:30])
        await msg.answer(text, parse_mode="HTML")
    except (IndexError, ValueError):
        await msg.answer("📝 Формат: /listaudio ID_категорії")


# ═══════════════════════════════════════════════════════════════════
# SETUP & LAUNCH
# ═══════════════════════════════════════════════════════════════════

async def main():
    await init_db()
    await bot.set_my_commands([
        BotCommand(command="start", description="🏠 Запустити бота"),
        BotCommand(command="profile", description="👤 Мій акаунт"),
        BotCommand(command="top10", description="🏆 ТОП 10"),
        BotCommand(command="faq", description="❓ FAQ"),
        BotCommand(command="ref", description="💸 Реферальне посилання"),
        BotCommand(command="cancel", description="❌ Скасувати"),
    ])
    logger.info("🤖 PrankBox запущено!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
