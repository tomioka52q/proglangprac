# Документация: модуль манги (Remanga)

> Этот документ описывает все классы, функции, хендлеры и клавиатуры, связанные со скачиванием манги через API Remanga (`api.remanga.org`).

---

## 1. Парсер — `remanga_parser.py`

### `API_URL`
```python
API_URL = "https://api.remanga.org/api"
```
Базовый URL для всех запросов к Remanga API.

---

### `class RemangaParser`

Асинхронный парсер для работы с мангой через `aiohttp`. Использует `ClientSession` с отключенной SSL-верификацией.

#### `__init__(self)`
Инициализирует парсер:
- `self.session = None` — сессия создается лениво
- `self.headers` — User-Agent: Chrome/120 на Windows

#### `async _get_session(self)`
Ленивое создание `aiohttp.ClientSession`. Если сессия не создана или закрыта — создает новую с заголовками и `ssl=False`.

#### `async close(self)`
Закрывает `ClientSession`, если она открыта. Вызывается в `finally` блоке `main()` в `bot.py`.

---

### `async search(self, query)`

**Запрос:** `GET /api/search/?query={query}`

**Что делает:**
- Ищет мангу по названию (русскому или английскому).
- Логирует `status` и количество результатов через `print`.
- При `status != 200` возвращает пустой список.

**Возвращает:** `list[dict]`, каждый элемент:
```python
{
    "id": str,          # dir (кодовое имя манги), например "tower-of-god"
    "title": str,       # rus_name или en_name
    "cover_url": str,   # https://remanga.org + img.high
    "year": int,        # issue_year
    "status": str,      # name из status (если dict)
    "chapters_count": int
}
```

**Обработка ошибок:** любое исключение → `print` + `return []`.

---

### `async get_title(self, manga_id)`

**Запрос:** `GET /api/titles/{manga_id}/`

**Что делает:**
- Загружает полную информацию о манге по `dir` (кодовому имени).

**Возвращает:** `dict | None`:
```python
{
    "id": str,
    "title": str,
    "cover_url": str,
    "description": str,
    "year": int,
    "status": str,
    "chapters_count": int
}
```

**Обработка ошибок:** `status != 200` или исключение → `return None`.

---

### `async get_chapters(self, manga_id)`

**Запросы:**
1. `GET /api/titles/{manga_id}/` — получает `branches[0]["id"]` (ID ветки перевода).
2. `GET /api/titles/chapters/?branch_id={id}&ordering=index&page={N}&count=100`

**Что делает:**
- Загружает главы пагинацией по 100 штук.
- Собирает все страницы в цикле `while True`.

**Возвращает:** `list[dict]`, каждый элемент:
```python
{
    "id": str,       # chapter ID для скачивания
    "number": float, # номер главы
    "volume": int,   # номер тома
    "name": str,     # название главы
    "pages_count": int
}
```

**Обработка ошибок:** любое исключение → `return []`.

---

### `async get_chapter_pages(self, chapter_id)`

**Запрос:** `GET /api/titles/chapters/{chapter_id}/`

**Что делает:**
- Получает список страниц (изображений) для конкретной главы.
- Поддерживает 4 формата данных в `pages`:
  - `str` — прямая ссылка
  - `list` — берет `first[0].get("link")`
  - `dict` — берет `link`, `url` или `image`
- Добавляет `https://remanga.org` если ссылка относительная.

**Возвращает:** `list[dict]`:
```python
{"number": int, "image_url": str}
```

---

### `async download_image(self, url)`

**Что делает:**
- Ждет `0.3` секунды (rate limiting).
- Скачивает изображение с `Referer: https://remanga.org/`.

**Возвращает:** `bytes` — бинарные данные картинки.

**При ошибке:** выбрасывает `Exception(f"Download failed: ...")`.

---

## 2. Утилиты скачивания — `download_utils.py`

### `DOWNLOADS_DIR`
```python
DOWNLOADS_DIR = "downloads"
```
Папка для временных файлов. Создается автоматически.

---

### `async save_temp_file(content, filename)`

Сохраняет бинарный контент в `downloads/{filename}` асинхронно через `aiofiles`.

**Возвращает:** полный путь к файлу.

---

### `async images_to_pdf(image_paths, output_filename)`

Конвертирует список изображений в PDF через `img2pdf`.

**Возвращает:** путь к PDF-файлу в `downloads/`.

---

### `async compress_image(image_path, quality=70)`

Сжимает JPEG через Pillow:
- Если размер > 2000px по большей стороне — уменьшает до 2000x2000 (`LANCZOS`).
- Сохраняет с `quality=70`, `optimize=True`.

**Возвращает:** путь к `_compressed.jpg`.

---

### `async cleanup_files(filepaths)`

Удаляет список файлов, игнорируя ошибки.

---

### `async download_chapter(chapter_id, manga_title, chapter_num, remanga_parser, progress_callback=None)`

**Алгоритм:**
1. Получает список страниц через `remanga_parser.get_chapter_pages(chapter_id)`.
2. Для каждой страницы:
   - вызывает `progress_callback(idx, total, "downloading")` если передан
   - скачивает изображение через `download_image()`
   - сохраняет во временный файл `page_{number}.jpg`
3. Вызывает `progress_callback(total, total, "creating_pdf")`.
4. Собирает PDF из всех изображений.
5. Если файл > 50 MB:
   - удаляет временные файлы
   - вызывает `download_chapter_compressed()` (со сжатием)
6. Иначе удаляет временные изображения и возвращает PDF.

---

### `async download_chapter_compressed(...)`

То же самое, но после скачивания каждой страницы вызывает `compress_image()`. Используется как fallback при превышении лимита 50 MB.

---

## 3. Клавиатуры — `keyboards.py`

### `get_manga_inline_keyboard(manga_list)`

**Callback data:** `manga_select_{idx}` (индекс, не ID манги).

Кнопки: по одной на строку с названием манги. Последняя кнопка — `🔙 Назад к поиску` (`manga_back`).

**Почему индекс:** Telegram ограничивает длину `callback_data` 64 байтами. `idx` короткий, а `manga['id']` (строка `dir`) может быть длинной.

---

### `get_manga_detail_keyboard(manga_id)`

Кнопки:
- `📖 По главам` → `manga_by_chapter:{manga_id}`
- `📚 По томам` → `manga_by_volume:{manga_id}`

---

### `get_chapters_keyboard(chapters, manga_id, page=0, per_page=20)`

Пагинация глав:
- Показывает `per_page=20` глав на страницу.
- Каждая кнопка: `Глава {num} - {name[:20]}` → `dlch:{manga_id}:{ch_id}:{ch_num}`
- Навигация: `⬅️ Назад` / `Вперёд ➡️` → `chpage:{manga_id}:{page±1}`

---

### `get_volumes_keyboard(volumes_dict, manga_id)`

Кнопки: `📖 Том {N} ({count} глав)` → `vol:{manga_id}:{vol_num}`

---

### `get_volume_chapters_keyboard(chapters, manga_id, volume_num)`

Кнопки:
- `📥 Скачать весь том {N}` → `vdl:{manga_id}:{volume_num}`
- Далее список глав с callback `dlch:{manga_id}:{ch_id}:{ch_num}`

---

## 4. Хендлеры бота — `bot.py`

### `@dp.message(lambda m: m.text == "🔍 Поиск манги")`

**`search_manga_handler(message, state)`**

Устанавливает состояние `States.enter_manga_name` и просит ввести название.

---

### `@dp.message(States.enter_manga_name)`

**`process_manga_name(message, state)`**

- Вызывает `remanga_parser.search(message.text)`.
- Создает `manga_map`: `{idx → manga_id}` — маппинг для callback'ов.
- Сохраняет в `FSMContext` через `state.update_data()`.
- Отправляет inline клавиатуру `get_manga_inline_keyboard(results)`.

---

### `@dp.callback_query(lambda c: c.data.startswith("manga_select_"))`

**`handle_manga_callback(callback, state)`**

- Извлекает `idx` из `callback.data`.
- Получает `manga_map` из `FSMContext`.
- Ищет `manga_id` по индексу. Если данных нет — просит выполнить поиск заново.
- Загружает детали через `remanga_parser.get_title(manga_id)`.
- Формирует caption:
  - `<b>title</b>`
  - Год, статус, количество глав
  - Описание (очищает HTML-теги через `re.sub(r'<[^>]+>', '')`, обрезает до 500 символов)
- Отправляет фото обложки (если есть) или текст с `get_manga_detail_keyboard(manga_id)`.
- Очищает состояние `state.clear()`.

---

### `@dp.callback_query(lambda c: c.data == "manga_back")`

**`handle_manga_back(callback, state)`**

Возвращает к вводу названия манги (`States.enter_manga_name`).

---

### `@dp.callback_query(lambda c: c.data.startswith("manga_by_chapter:"))`

**`handle_manga_by_chapter(callback, state)`**

- `manga_id = callback.data.split(":")[1]`
- Загружает главы через `remanga_parser.get_chapters()`.
- Сортирует по номеру главы.
- Сохраняет `chapters` и `manga_id` в `FSMContext`.
- Отправляет `get_chapters_keyboard(chapters, manga_id, page=0)`.

---

### `@dp.callback_query(lambda c: c.data.startswith("chpage:"))`

**`handle_chapters_page(callback, state)`**

- `parts = callback.data.split(":")` → `[chpage, manga_id, page]`
- Берет `chapters` из `FSMContext`.
- Если данных нет — просит выполнить поиск заново.
- Редактирует сообщение через `edit_text` с новой страницей `get_chapters_keyboard(..., page=page)`.

---

### `@dp.callback_query(lambda c: c.data.startswith("dlch:"))`

**`handle_download_chapter(callback)`**

- **Важно:** сразу вызывает `callback.answer()` чтобы не получить `query is too old`.
- Распаковывает `dlch:{manga_id}:{chapter_id}:{chapter_num}`.
- Получает информацию о манге через `get_title()`.
- Отправляет сообщение-прогресс `⏳ Скачиваю главу X...`.

**`update_progress(current, total, status)`** (вложенная функция):
- `status == "downloading"`: считает процент `(current/total)*100`, строит прогресс-бар из 10 символов `▰`/`▱`, редактирует сообщение.
- `status == "creating_pdf"`: меняет текст на `📄 Создаю PDF...`

**Основной flow:**
1. Вызывает `download_chapter(chapter_id, manga['title'], chapter_num, remanga_parser, progress_callback=update_progress)`.
2. Получает `pdf_path`.
3. Проверяет размер:
   - `> 50 MB` → `msg.edit_text("⚠️ Файл слишком большой...")`
   - `<= 50 MB` → отправляет `FSInputFile(pdf_path)` с caption, удаляет progress-сообщение.
4. В `finally` удаляет `pdf_path` с диска.

---

### `@dp.callback_query(lambda c: c.data.startswith("manga_by_volume:"))`

**`handle_manga_by_volume(callback, state)`**

- `manga_id = callback.data.split(":")[1]`
- Загружает главы через `remanga_parser.get_chapters()`.
- Группирует по полю `volume` (том) в `volumes_dict: {vol_num → [chapters]}`.
- Если томов нет → `callback.answer("Тома не найдены")`.
- Сохраняет `volumes_dict` и `manga_id` в `FSMContext`.
- Формирует текст: `📚 Выберите том (N глав всего):` + список томов.
- Отправляет `get_volumes_keyboard(volumes_dict, manga_id)`.

---

### `@dp.callback_query(lambda c: c.data.startswith("vol:"))`

**`handle_volume_chapters(callback, state)`**

- `parts = callback.data.split(":")` → `[vol, manga_id, volume_num]`
- Берет `volumes_dict` из `FSMContext`.
- Если тома нет → "Данные не найдены".
- Сортирует главы по номеру.
- Отправляет `get_volume_chapters_keyboard(volume_chapters, manga_id, volume_num)`.

---

### `@dp.callback_query(lambda c: c.data.startswith("vdl:"))`

**`handle_volume_download(callback)`**

- **Важно:** сразу вызывает `callback.answer()`.
- `parts = callback.data.split(":")` → `[vdl, manga_id, volume_num]`
- Получает информацию о манге через `get_title()`.
- Отправляет `⏳ Скачиваю том {N}...`.
- Загружает главы, фильтрует по `volume == volume_num`, сортирует по `number`.
- В цикле для каждой главы:
  - Вызывает `download_chapter(ch["id"], manga["title"], ch["number"], remanga_parser)`
  - Проверяет размер (> 50 MB → skip)
  - Отправляет PDF с caption: `{title} - Том {N}, Глава {X} ({size} МБ)`
  - Удаляет файл после отправки
  - Считает `downloaded += 1`
- В конце: `✅ Скачано {downloaded} глав из тома {volume_num}`.

---

## 5. Callback Data схема

| Callback | Формат | Описание |
|----------|--------|----------|
| `manga_select_{idx}` | `manga_select_0` | Выбор манги из результатов поиска |
| `manga_back` | `manga_back` | Вернуться к вводу названия манги |
| `manga_by_chapter:{id}` | `manga_by_chapter:tower-of-god` | Показать главы манги |
| `manga_by_volume:{id}` | `manga_by_volume:tower-of-god` | Показать тома манги |
| `chpage:{id}:{page}` | `chpage:tower-of-god:2` | Страница пагинации глав |
| `dlch:{id}:{ch_id}:{num}` | `dlch:tower-of-god:12345:15.5` | Скачать конкретную главу |
| `vol:{id}:{vol_num}` | `vol:tower-of-god:3` | Выбор тома |
| `vdl:{id}:{vol_num}` | `vdl:tower-of-god:3` | Скачать весь том |

---

## 6. Архитектура потока манги

```
Пользователь
    │
    ▼
[🔍 Поиск манги] ──► search_manga_handler ──► States.enter_manga_name
    │
    ▼
Ввод названия ──► process_manga_name ──► remanga_parser.search()
    │
    ▼
[get_manga_inline_keyboard] ──► Пользователь выбирает мангу
    │
    ▼
manga_select_{idx} ──► handle_manga_callback
    │
    ▼
[get_manga_detail_keyboard]
    │
    ├──► 📖 По главам ──► manga_by_chapter ──► get_chapters_keyboard
    │       │
    │       └──► dlch:... ──► handle_download_chapter ──► download_chapter ──► PDF
    │
    └──► 📚 По томам ──► manga_by_volume ──► get_volumes_keyboard
            │
            └──► vol:... ──► get_volume_chapters_keyboard
                    │
                    ├──► dlch:... ──► скачать одну главу
                    └──► vdl:... ──► handle_volume_download ──► скачать все главы тома
```

---

## 7. Зависимости модуля манги

```
remanga_parser.py
├── aiohttp

download_utils.py
├── aiofiles
├── img2pdf
├── Pillow (PIL)

keyboards.py (манга)
├── aiogram.types (InlineKeyboardMarkup, InlineKeyboardButton, ...)
├── aiogram.utils.keyboard (InlineKeyboardBuilder)

bot.py (манга-хендлеры)
├── aiogram
├── remanga_parser.RemangaParser
├── download_utils.download_chapter
└── keyboards (get_manga_inline_keyboard, get_manga_detail_keyboard,
              get_chapters_keyboard, get_volumes_keyboard,
              get_volume_chapters_keyboard)
```

---

## 8. Известные особенности и ограничения

1. **Rate limiting:** `download_image()` ждет `0.3` секунды между запросами картинок.
2. **Лимит Telegram:** файлы > 50 MB не отправляются (проверка `size > 50 * 1024 * 1024`).
3. **Callback timeout:** `callback.answer()` вызывается в начале долгих операций (`dlch`, `vdl`) чтобы избежать `query is too old`.
4. **SSL:** отключен (`ssl=False`) для `aiohttp` из-за возможных проблем с сертификатами Remanga.
5. **Пагинация:** главы показываются по 20 на страницу (`per_page=20`).
6. **Fallback на сжатие:** если PDF > 50 MB, автоматически перекачивается со сжатием JPEG (`quality=70`).
