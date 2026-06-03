from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton


def main_menu():
    """Main bot menu keyboard."""
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="😆 Розіграші"), KeyboardButton(text="📞 Пранк-дзвінки")],
        [KeyboardButton(text="🏆 ТОП 10"), KeyboardButton(text="🌀 Випадкові")],
        [KeyboardButton(text="📢 Поділитися ботом"), KeyboardButton(text="💸 Заробити")],
        [KeyboardButton(text="👤 Мій акаунт"), KeyboardButton(text="ℹ️ Про бота")],
    ], resize_keyboard=True)


def pranks_menu():
    """Pranks submenu keyboard."""
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📝 Категорії"), KeyboardButton(text="👦👩 Іменні")],
        [KeyboardButton(text="🎉 Свята"), KeyboardButton(text="🔍 Пошук")],
        [KeyboardButton(text="🏁 Головне меню")],
    ], resize_keyboard=True)


def category_page_kb(cats: list, page: int, total_pages: int, group: str):
    """Inline keyboard for category page with pagination."""
    buttons = []
    row = []
    for c in cats:
        row.append(InlineKeyboardButton(text=c["name"], callback_data=f"cat_{c['id']}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    # Pagination
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"pg_{group}_{page-1}"))
    nav.append(InlineKeyboardButton(text=f"📄 {page+1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="Далі ▶️", callback_data=f"pg_{group}_{page+1}"))
    if nav:
        buttons.append(nav)

    buttons.append([InlineKeyboardButton(text="↩️ Назад до меню", callback_data="change_cat")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def prank_list_kb(pranks: list, cat_id: int, page: int, total_count: int, per_page: int = 10):
    """Inline keyboard showing a list of pranks in a category with pagination."""
    buttons = []
    for p in pranks:
        buttons.append([
            InlineKeyboardButton(text=f"▶️ {p['title']}", callback_data=f"play_{p['id']}"),
            InlineKeyboardButton(text="📢", callback_data=f"share_{p['id']}"),
        ])

    # Pagination
    total_pages = (total_count + per_page - 1) // per_page
    if total_pages > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton(text="◀️", callback_data=f"clist_{cat_id}_{page-1}"))
        nav.append(InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="noop"))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton(text="▶️", callback_data=f"clist_{cat_id}_{page+1}"))
        buttons.append(nav)

    buttons.append([InlineKeyboardButton(text="↩️ Назад до категорій", callback_data=f"backcat_{cat_id}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def prank_audio_kb(prank_id: int):
    """Buttons shown under a played audio — share bot."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📢 Поділитися ботом", callback_data=f"share_{prank_id}"),
        ]
    ])


def top_prank_kb(prank_id: int):
    """Inline buttons for a prank in the top list."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="▶️ Слухати", callback_data=f"play_{prank_id}"),
            InlineKeyboardButton(text="📢", callback_data=f"share_{prank_id}"),
        ]
    ])


def about_kb():
    """About bot inline keyboard."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="show_stats")],
        [InlineKeyboardButton(text="❓ FAQ", callback_data="show_faq")],
    ])


def call_scenarios_kb():
    """Inline keyboard with call scenarios."""
    from call_provider import CALL_SCENARIOS
    buttons = []
    for key, info in CALL_SCENARIOS.items():
        buttons.append([InlineKeyboardButton(
            text=f"{info['emoji']} {info['name']}",
            callback_data=f"callsc_{key}"
        )])
    buttons.append([InlineKeyboardButton(text="🏁 Скасувати", callback_data="call_cancel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def call_confirm_kb(call_id: int):
    """Confirm & pay button for a call."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ Оплатити", callback_data=f"callpay_{call_id}")],
        [InlineKeyboardButton(text="❌ Скасувати", callback_data="call_cancel")],
    ])
