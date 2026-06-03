from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

def main_menu():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🏆 ТОП 10"), KeyboardButton(text="😆 Розіграші")],
        [KeyboardButton(text="👤 Мій акаунт"), KeyboardButton(text="💰 Поповнити баланс")],
        [KeyboardButton(text="💸 Заробити"), KeyboardButton(text="❓ FAQ")],
    ], resize_keyboard=True)

def pranks_menu():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📝 Категорії"), KeyboardButton(text="👦👩 Іменні")],
        [KeyboardButton(text="🎉 Свята"), KeyboardButton(text="🌀 Випадкові записи")],
        [KeyboardButton(text="❤️ Обране"), KeyboardButton(text="🏁 Головне меню")],
    ], resize_keyboard=True)

def category_page_kb(cats: list, page: int, total_pages: int, group: str):
    """Build inline keyboard for a category page with pagination."""
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
        nav.append(InlineKeyboardButton(text="◀ Назад", callback_data=f"pg_{group}_{page-1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="Далее ▶", callback_data=f"pg_{group}_{page+1}"))
    if nav:
        buttons.append(nav)
    # Change category button
    buttons.append([InlineKeyboardButton(text="↩️ Змінити категорію", callback_data="change_cat")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def prank_card_kb(prank_id: int, cat_id: int, index: int, total: int):
    """Buttons for a single prank audio card."""
    row1 = [InlineKeyboardButton(text="▶ Слухати", callback_data=f"play_{prank_id}")]
    row2 = [
        InlineKeyboardButton(text="❤️ В обране", callback_data=f"fav_{prank_id}"),
        InlineKeyboardButton(text="📤 Надіслати", switch_inline_query=f"prank_{prank_id}"),
    ]
    row3 = []
    if index > 0:
        row3.append(InlineKeyboardButton(text="⬅ Попереднє", callback_data=f"pnav_{cat_id}_{index-1}"))
    if index < total - 1:
        row3.append(InlineKeyboardButton(text="Наступне ➡", callback_data=f"pnav_{cat_id}_{index+1}"))
    row4 = [InlineKeyboardButton(text="🔙 Назад до категорії", callback_data=f"backcat_{cat_id}")]
    kb = [row1, row2]
    if row3: kb.append(row3)
    kb.append(row4)
    return InlineKeyboardMarkup(inline_keyboard=kb)

def admin_cat_kb(cats: list):
    """Admin: choose category for new audio."""
    buttons = [[InlineKeyboardButton(text=c["name"], callback_data=f"acat_{c['id']}")] for c in cats[:20]]
    if len(cats) > 20:
        buttons += [[InlineKeyboardButton(text=c["name"], callback_data=f"acat_{c['id']}")] for c in cats[20:]]
    buttons.append([InlineKeyboardButton(text="❌ Скасувати", callback_data="acancel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def admin_prank_kb(prank_id: int):
    """Admin: actions for a single prank."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Перейменувати", callback_data=f"arename_{prank_id}"),
         InlineKeyboardButton(text="📂 Змінити категорію", callback_data=f"achcat_{prank_id}")],
        [InlineKeyboardButton(text="🔄 Замінити аудіо", callback_data=f"areplace_{prank_id}"),
         InlineKeyboardButton(text="🗑 Видалити", callback_data=f"adel_{prank_id}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")],
    ])
