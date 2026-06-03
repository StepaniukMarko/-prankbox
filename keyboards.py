from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton


def main_menu():
    """Main bot menu keyboard."""
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="😆 Розіграші"), KeyboardButton(text="🏆 ТОП 10")],
        [KeyboardButton(text="❤️ Обране"), KeyboardButton(text="🌀 Випадкові")],
        [KeyboardButton(text="💸 Заробити"), KeyboardButton(text="👤 Мій акаунт")],
        [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="ℹ️ Про бота")],
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


def prank_card_kb(prank_id: int, cat_id: int, index: int, total: int):
    """Inline keyboard for a single prank card."""
    row1 = [InlineKeyboardButton(text="▶️ Слухати", callback_data=f"play_{prank_id}")]
    row2 = [
        InlineKeyboardButton(text="❤️ В обране", callback_data=f"fav_{prank_id}"),
        InlineKeyboardButton(text="📤 Надіслати", switch_inline_query=f"prank_{prank_id}"),
    ]

    # Navigation
    row3 = []
    if index > 0:
        row3.append(InlineKeyboardButton(text="⬅️", callback_data=f"pnav_{cat_id}_{index-1}"))
    row3.append(InlineKeyboardButton(text=f"{index+1}/{total}", callback_data="noop"))
    if index < total - 1:
        row3.append(InlineKeyboardButton(text="➡️", callback_data=f"pnav_{cat_id}_{index+1}"))

    row4 = [InlineKeyboardButton(text="🔙 До категорії", callback_data=f"backcat_{cat_id}")]

    kb = [row1, row2]
    if row3:
        kb.append(row3)
    kb.append(row4)
    return InlineKeyboardMarkup(inline_keyboard=kb)


def top_prank_kb(prank_id: int):
    """Inline buttons for a prank in the top list."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="▶️ Слухати", callback_data=f"play_{prank_id}"),
            InlineKeyboardButton(text="❤️", callback_data=f"fav_{prank_id}"),
        ]
    ])


def favorites_empty_kb():
    """Keyboard when favorites are empty."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="😆 До розіграшів", callback_data="go_pranks")]
    ])


def about_kb():
    """About bot inline keyboard."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="show_stats")],
        [InlineKeyboardButton(text="❓ FAQ", callback_data="show_faq")],
    ])
