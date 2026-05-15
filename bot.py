import asyncio
import os
import re

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, FSInputFile

from remanga_parser import RemangaParser
from keyboards import (
    get_manga_inline_keyboard,
    get_main_keyboard,
    get_manga_detail_keyboard, get_chapters_keyboard,
    get_volumes_keyboard, get_volume_chapters_keyboard,
    get_books_inline_keyboard, get_book_format_keyboard
)
from download_utils import download_chapter
from coolib_parser import CoolibParser

BOT_TOKEN = "8609460139:AAHY3lbEomepYMEfDbeEE3mIRoiw9qfMRlc"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

remanga_parser = RemangaParser()
coolib_parser = CoolibParser()


class States(StatesGroup):
    enter_name = State()
    enter_manga_name = State()


# Временное хранилище результатов поиска книг
user_book_results = {}


# ==================== Handlers ====================
@dp.message(Command("start"))
async def start_command(message: types.Message):
    user_name = message.from_user.first_name
    await message.answer(
        f"Привет, {user_name}! 👋\n\n"
        f"Выбери действие с помощью кнопок внизу экрана:",
        reply_markup=get_main_keyboard()
    )


@dp.message(lambda message: message.text == "🔍 Поиск книги")
async def search_book_handler(message: types.Message, state: FSMContext):
    await state.set_state(States.enter_name)
    await message.answer("Введите книгу, которую хотите найти")


@dp.message(States.enter_name)
async def process_name(message: Message, state: FSMContext):
    # Используем новый парсер
    found_books = await asyncio.to_thread(coolib_parser.search_book, message.text)

    if found_books:
        # Сохраняем результаты поиска
        user_book_results[message.from_user.id] = found_books
        await message.answer(
            f"🔍 Результат поиска по запросу '{message.text}':",
            reply_markup=get_books_inline_keyboard(found_books)
        )
        await state.clear()
    else:
        await message.answer(f"❌ По запросу '{message.text}' ничего не найдено, проверьте правильность"
                             f" написанного текста или введите полное название")


@dp.callback_query(lambda c: c.data.startswith("book_select_"))
async def handle_book_select_callback(callback: types.CallbackQuery, state: FSMContext):
    """Обработка выбора книги"""
    book_id = int(callback.data.replace("book_select_", ""))

    user_books = user_book_results.get(callback.from_user.id, [])
    selected_book = next((b for b in user_books if b.id == book_id), None)
    if not selected_book:
        await callback.answer("Книга не найдена", show_alert=True)
        return

    if not selected_book.download_url or not selected_book.format_type:
        await callback.answer("Ссылка на скачивание отсутствует", show_alert=True)
        return

    # Сохраняем выбранную книгу
    await state.update_data(selected_book=selected_book)

    keyboard = get_book_format_keyboard(book_id)

    await callback.message.edit_text(
        f"📚 {selected_book.name}\n\n"
        f"Нажмите кнопку для скачивания в PDF:",
        reply_markup=keyboard
    )
    await callback.answer()


@dp.callback_query(lambda c: c.data.startswith("book_download_"))
async def handle_book_download_callback(callback: types.CallbackQuery, state: FSMContext):
    """Обработка скачивания книги"""
    await callback.answer()
    parts = callback.data.split("_")
    book_id = int(parts[2])
    format_type = parts[3]

    user_books = user_book_results.get(callback.from_user.id, [])
    selected_book = next((b for b in user_books if b.id == book_id), None)
    if not selected_book:
        await callback.answer("Книга не найдена", show_alert=True)
        return

    # Отправляем сообщение о начале скачивания
    msg = await callback.message.answer(f"⏳ Скачиваю книгу в формате {format_type.upper()}...")

    try:
        # Скачиваем книгу в отдельном потоке, чтобы не блокировать бота
        file_path = await asyncio.to_thread(coolib_parser.download_book, selected_book, format_type)

        if file_path and os.path.exists(file_path):
            size = os.path.getsize(file_path)
            size_mb = size / (1024 * 1024)

            if size > 50 * 1024 * 1024:
                await msg.edit_text(f"⚠️ Файл слишком большой ({size_mb:.1f} МБ), не могу отправить в Telegram")
            else:
                # Отправляем файл пользователю
                document = FSInputFile(file_path)
                await callback.message.answer_document(
                    document,
                    caption=f"✅ **{selected_book.name}**\n\nФормат: {format_type.upper()}\nРазмер: {size_mb:.1f} МБ",
                    parse_mode="HTML"
                )
                await msg.delete()

            # Удаляем временный файл
            try:
                os.remove(file_path)
            except:
                pass
        else:
            await msg.edit_text("❌ Ошибка при скачивании книги. Попробуйте позже.")

    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)}")


@dp.callback_query(lambda c: c.data == "book_back_to_search")
async def handle_book_back_to_search(callback: types.CallbackQuery, state: FSMContext):
    """Возврат к поиску книг"""
    await state.set_state(States.enter_name)
    await callback.message.edit_text("Введите книгу, которую хотите найти")
    await callback.answer()


@dp.message(lambda message: message.text == "🔍 Поиск манги")
async def search_manga_handler(message: types.Message, state: FSMContext):
    await state.set_state(States.enter_manga_name)
    await message.answer("Введите название манги, которую хотите найти")


@dp.message(States.enter_manga_name)
async def process_manga_name(message: Message, state: FSMContext):
    results = await remanga_parser.search(message.text)
    if results:
        manga_map = {str(idx): manga['id'] for idx, manga in enumerate(results)}
        await state.update_data(manga_map=manga_map)
        await message.answer(f"🔍 Результат поиска манги по запросу '{message.text}':",
                             reply_markup=get_manga_inline_keyboard(results))
    else:
        await message.answer(f"❌ По запросу '{message.text}' ничего не найдено, проверьте правильность"
                             f" написанного текста или введите полное название")


@dp.callback_query(lambda c: c.data.startswith("manga_select_"))
async def handle_manga_callback(callback: types.CallbackQuery, state: FSMContext):
    idx = callback.data.replace("manga_select_", "")
    data = await state.get_data()
    manga_map = data.get("manga_map", {})
    manga_id = manga_map.get(idx)

    if not manga_id:
        await callback.answer("Данные устарели, выполните поиск заново", show_alert=True)
        return

    manga = await remanga_parser.get_title(manga_id)
    if not manga:
        await callback.answer("Не удалось загрузить информацию", show_alert=True)
        await state.clear()
        return

    caption = f"<b>{manga['title']}</b>\n"
    if manga['year']:
        caption += f"Год: {manga['year']}\n"
    if manga['status']:
        caption += f"Статус: {manga['status']}\n"
    if manga['chapters_count']:
        caption += f"Глав: {manga['chapters_count']}\n"
    if manga['description']:
        desc = re.sub(r'<[^>]+>', '', manga['description'])
        desc = desc[:500] + "..." if len(desc) > 500 else desc
        caption += f"\n{desc}"

    if manga['cover_url']:
        await callback.message.answer_photo(
            manga['cover_url'],
            caption=caption,
            parse_mode="HTML",
            reply_markup=get_manga_detail_keyboard(manga_id)
        )
    else:
        await callback.message.answer(
            caption,
            parse_mode="HTML",
            reply_markup=get_manga_detail_keyboard(manga_id)
        )
    await callback.answer()
    await state.clear()


@dp.callback_query(lambda c: c.data == "manga_back")
async def handle_manga_back(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(States.enter_manga_name)
    await callback.message.answer("Введите название манги, которую хотите найти")
    await callback.answer()


@dp.callback_query(lambda c: c.data.startswith("manga_by_chapter:"))
async def handle_manga_by_chapter(callback: types.CallbackQuery, state: FSMContext):
    manga_id = callback.data.split(":")[1]
    chapters = await remanga_parser.get_chapters(manga_id)
    if not chapters:
        await callback.answer("Главы не найдены", show_alert=True)
        return

    chapters = sorted(chapters, key=lambda x: x["number"])
    await state.update_data(chapters=chapters, manga_id=manga_id)

    keyboard = get_chapters_keyboard(chapters, manga_id, page=0)
    await callback.message.answer(f"📖 Выберите главу ({len(chapters)} всего):", reply_markup=keyboard)
    await callback.answer()


@dp.callback_query(lambda c: c.data.startswith("chpage:"))
async def handle_chapters_page(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    manga_id = parts[1]
    page = int(parts[2])
    data = await state.get_data()
    chapters = data.get("chapters", [])
    if not chapters:
        await callback.answer("Данные устарели", show_alert=True)
        return
    keyboard = get_chapters_keyboard(chapters, manga_id, page=page)
    await callback.message.edit_text(f"📖 Выберите главу ({len(chapters)} всего):", reply_markup=keyboard)
    await callback.answer()


@dp.callback_query(lambda c: c.data.startswith("dlch:"))
async def handle_download_chapter(callback: types.CallbackQuery):
    await callback.answer()
    parts = callback.data.split(":")
    manga_id = parts[1]
    chapter_id = parts[2]
    chapter_num = parts[3]

    manga = await remanga_parser.get_title(manga_id)
    if not manga:
        await callback.answer("Манга не найдена", show_alert=True)
        return

    msg = await callback.message.answer(f"⏳ Скачиваю главу {chapter_num}...\n\n▱▱▱▱▱▱▱▱▱▱ 0%")

    async def update_progress(current, total, status):
        try:
            if status == "downloading":
                percent = int((current / total) * 100)
                filled = int((current / total) * 10)
                bar = "▰" * filled + "▱" * (10 - filled)
                text = f"⏳ Скачиваю главу {chapter_num}...\n\n{bar} {percent}%\nСтраница {current}/{total}"
                await msg.edit_text(text)
            elif status == "creating_pdf":
                await msg.edit_text(f"📄 Создаю PDF для главы {chapter_num}...")
        except Exception:
            pass

    try:
        pdf_path = await download_chapter(chapter_id, manga['title'], chapter_num, remanga_parser,
                                          progress_callback=update_progress)
        size = os.path.getsize(pdf_path)
        size_mb = size / (1024 * 1024)

        if size > 50 * 1024 * 1024:
            await msg.edit_text(f"⚠️ Файл слишком большой ({size_mb:.1f} МБ)")
        else:
            document = FSInputFile(pdf_path)
            await callback.message.answer_document(document,
                                                   caption=f"{manga['title']} - Глава {chapter_num} ({size_mb:.1f} МБ)")
            try:
                await msg.delete()
            except Exception:
                pass
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {e}")
    finally:
        try:
            if 'pdf_path' in locals() and os.path.exists(pdf_path):
                os.remove(pdf_path)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data.startswith("manga_by_volume:"))
async def handle_manga_by_volume(callback: types.CallbackQuery, state: FSMContext):
    manga_id = callback.data.split(":")[1]
    chapters = await remanga_parser.get_chapters(manga_id)
    if not chapters:
        await callback.answer("Главы не найдены", show_alert=True)
        return

    volumes_dict = {}
    for ch in chapters:
        vol = ch.get("volume")
        if vol is not None:
            volumes_dict.setdefault(vol, []).append(ch)

    if not volumes_dict:
        await callback.answer("Тома не найдены", show_alert=True)
        return

    await state.update_data(volumes_dict=volumes_dict, current_manga_id=manga_id)

    text = f"📚 Выберите том ({sum(len(c) for c in volumes_dict.values())} глав всего):\n\n"
    for vol_num in sorted(volumes_dict.keys()):
        text += f"Том {vol_num}: {len(volumes_dict[vol_num])} глав\n"

    keyboard = get_volumes_keyboard(volumes_dict, manga_id)
    await callback.message.answer(text, reply_markup=keyboard)
    await callback.answer()


@dp.callback_query(lambda c: c.data.startswith("vol:"))
async def handle_volume_chapters(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    manga_id = parts[1]
    volume_num = int(parts[2])

    data = await state.get_data()
    volumes_dict = data.get("volumes_dict", {})
    if volume_num not in volumes_dict:
        await callback.answer("Данные не найдены", show_alert=True)
        return

    volume_chapters = sorted(volumes_dict[volume_num], key=lambda x: x["number"])
    keyboard = get_volume_chapters_keyboard(volume_chapters, manga_id, volume_num)
    await callback.message.answer(f"📖 Том {volume_num} ({len(volume_chapters)} глав):", reply_markup=keyboard)
    await callback.answer()


@dp.callback_query(lambda c: c.data.startswith("vdl:"))
async def handle_volume_download(callback: types.CallbackQuery):
    await callback.answer()
    parts = callback.data.split(":")
    manga_id = parts[1]
    volume_num = int(parts[2])

    manga = await remanga_parser.get_title(manga_id)
    if not manga:
        await callback.message.answer("Манга не найдена")
        await callback.answer()
        return

    await callback.message.answer(f"⏳ Скачиваю том {volume_num}...")

    chapters = await remanga_parser.get_chapters(manga_id)
    volume_chapters = [ch for ch in chapters if ch.get("volume") == volume_num]
    volume_chapters = sorted(volume_chapters, key=lambda x: x["number"])

    downloaded = 0
    for ch in volume_chapters:
        try:
            pdf_path = await download_chapter(ch["id"], manga["title"], ch["number"], remanga_parser)
            size = os.path.getsize(pdf_path)
            size_mb = size / (1024 * 1024)
            if size > 50 * 1024 * 1024:
                await callback.message.answer(f"⚠️ Глава {ch['number']} слишком большая ({size_mb:.1f} МБ)")
                continue
            document = FSInputFile(pdf_path)
            await callback.message.answer_document(document,
                                                   caption=f"{manga['title']} - Том {volume_num}, Глава {ch['number']} ({size_mb:.1f} МБ)")
            downloaded += 1
            try:
                os.remove(pdf_path)
            except Exception:
                pass
        except Exception:
            pass

    await callback.message.answer(f"✅ Скачано {downloaded} глав из тома {volume_num}")


@dp.message(lambda message: message.text == "👤 Профиль")
async def profile(message: types.Message):
    await message.answer("👤 Ваш профиль:\nИмя: {}\nID: {}".format(
        message.from_user.first_name, message.from_user.id
    ))


@dp.message(lambda message: message.text == "🆘 Помощь")
async def help_button(message: types.Message):
    await message.answer("❓ Напишите /start чтобы увидеть меню\nИли задайте вопрос @TOmiokaqqq.")


@dp.callback_query()
async def handle_callback(callback: types.CallbackQuery):
    if callback.data == "agree":
        await callback.message.answer("😊 Спасибо! Рады что вам нравится!")
        await callback.answer()
    elif callback.data == "disagree":
        await callback.message.answer("😔 Жаль! Что можно улучшить? Напишите в поддержку.")
        await callback.answer()
    else:
        await callback.answer("Неизвестная команда", show_alert=True)


@dp.message()
async def echo(message: types.Message):
    await message.answer(f"Ты написал: {message.text}\n\nИспользуй /start для меню или нажми кнопку 🆘 Помощь.")


async def main():
    print("Бот запущен...")
    await bot.delete_webhook(drop_pending_updates=True)
    try:
        await dp.start_polling(bot)
    finally:
        await remanga_parser.close()
        coolib_parser.close()


if __name__ == "__main__":
    asyncio.run(main())