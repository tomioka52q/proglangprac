from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def get_manga_inline_keyboard(manga_list):
    buttons = [
        [InlineKeyboardButton(text=manga["title"], callback_data=f"manga_select_{idx}")]
        for idx, manga in enumerate(manga_list)
    ]
    buttons.append([InlineKeyboardButton(text="🔙 Назад к поиску", callback_data="manga_back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_main_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="🆘 Помощь")],
            [KeyboardButton(text="🔍 Поиск книги"), KeyboardButton(text="🔍 Поиск манги")]
        ],
        resize_keyboard=True
    )
    return keyboard


def get_manga_detail_keyboard(manga_id):
    builder = InlineKeyboardBuilder()
    builder.button(text="📖 По главам", callback_data=f"manga_by_chapter:{manga_id}")
    builder.button(text="📚 По томам", callback_data=f"manga_by_volume:{manga_id}")
    builder.adjust(1)
    return builder.as_markup()


def get_chapters_keyboard(chapters, manga_id, page=0, per_page=20):
    builder = InlineKeyboardBuilder()
    start = page * per_page
    end = start + per_page
    page_chapters = chapters[start:end]

    for ch in page_chapters:
        ch_num = ch.get("number", "?")
        ch_name = ch.get("name", "")
        display = f"Глава {ch_num}" + (f" - {ch_name[:20]}" if ch_name else "")
        builder.button(text=display, callback_data=f"dlch:{manga_id}:{ch['id']}:{ch_num}")

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"chpage:{manga_id}:{page - 1}"))
    if end < len(chapters):
        nav.append(InlineKeyboardButton(text="Вперёд ➡️", callback_data=f"chpage:{manga_id}:{page + 1}"))
    if nav:
        builder.row(*nav)

    builder.adjust(1)
    return builder.as_markup()


def get_volumes_keyboard(volumes_dict, manga_id):
    builder = InlineKeyboardBuilder()
    for vol_num in sorted(volumes_dict.keys()):
        ch_count = len(volumes_dict[vol_num])
        builder.button(text=f"📖 Том {vol_num} ({ch_count} глав)", callback_data=f"vol:{manga_id}:{vol_num}")
    builder.adjust(1)
    return builder.as_markup()


def get_volume_chapters_keyboard(chapters, manga_id, volume_num):
    builder = InlineKeyboardBuilder()
    builder.button(text=f"📥 Скачать весь том {volume_num}", callback_data=f"vdl:{manga_id}:{volume_num}")
    for ch in chapters:
        ch_num = ch.get("number", "?")
        ch_name = ch.get("name", "")
        display = f"Глава {ch_num}" + (f" - {ch_name[:20]}" if ch_name else "")
        builder.button(text=display, callback_data=f"dlch:{manga_id}:{ch['id']}:{ch_num}")
    builder.adjust(1)
    return builder.as_markup()


def get_books_inline_keyboard(books_list):
    """
    Создание инлайн клавиатуры для выбора книги из результатов поиска
    """
    builder = InlineKeyboardBuilder()

    for book in books_list:
        # Ограничиваем длину названия до 50 символов для кнопки
        display_name = book.name[:50] + "..." if len(book.name) > 50 else book.name
        builder.button(text=f"📖 {display_name}", callback_data=f"book_select_{book.id}")

    builder.adjust(1)  # По одной кнопке в строке
    return builder.as_markup()


def get_book_format_keyboard(book_id):
    """Инлайн клавиатура для скачивания книги в PDF"""
    builder = InlineKeyboardBuilder()

    builder.button(
        text="📕 Скачать в PDF",
        callback_data=f"book_download_{book_id}_pdf"
    )
    builder.button(text="🔙 Назад к поиску", callback_data="book_back_to_search")

    builder.adjust(1)
    return builder.as_markup()