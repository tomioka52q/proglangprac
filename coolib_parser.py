import urllib.parse
import re
import os
import tempfile
import shutil
import zipfile
from pathlib import Path

import httpx
from bs4 import BeautifulSoup


class Book:
    def __init__(self, name: str, id: int, download_url: str = None, format_type: dict = None):
        self.name = name
        self.id = id
        self.download_url = download_url
        self.format_type = format_type or {}


class CoolibParser:
    def __init__(self):
        self.base_url = "https://coollib.net"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8"
        }
        self.session = httpx.Client(timeout=30, follow_redirects=True, verify=False, headers=headers)

    def search_book(self, book_name: str, limit: int = 10):
        """Поиск книги на Coollib"""
        query = urllib.parse.quote_plus(book_name)
        search_url = f"{self.base_url}/booksearch?ask={query}"

        try:
            response = self.session.get(search_url)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')
            raw_books = []
            seen_ids = set()

            # Ищем все ссылки на книги /b/ID
            for link in soup.find_all('a', href=True):
                href = link.get('href', '')
                if not href.startswith('/b/'):
                    continue

                # Извлекаем ID: /b/12345 или /b/12345-название
                parts = [p for p in href.split('/') if p]
                if len(parts) < 2 or not parts[1].split('-')[0].isdigit():
                    continue
                book_id = int(parts[1].split('-')[0])

                if book_id in seen_ids:
                    continue
                seen_ids.add(book_id)

                title = link.get_text(strip=True)
                if not title:
                    continue

                book_url = self.base_url + href if href.startswith('/') else href

                # Ищем автора рядом
                author = "Неизвестен"
                parent = link.find_parent(['div', 'li', 'td', 'p'])
                if parent:
                    author_link = parent.find('a', href=re.compile(r'^/a/\d+'))
                    if author_link:
                        author = author_link.get_text(strip=True)

                raw_books.append((title, author, book_id, book_url))

            # Фильтруем по релевантности запроса (убираем книги из боковой панели/тегов)
            query_words = set(book_name.lower().split())
            scored = []
            for title, author, book_id, book_url in raw_books:
                title_lower = title.lower()
                score = sum(1 for word in query_words if word in title_lower)
                if score > 0:
                    scored.append((score, title, author, book_id, book_url))

            # Сортируем: сначала точные совпадения
            scored.sort(key=lambda x: x[0], reverse=True)

            # Проверяем форматы только для топ-N книг
            books = []
            for score, title, author, book_id, book_url in scored[:limit]:
                formats = self._get_available_formats(book_url)
                if not formats:
                    formats = self._get_formats_fallback(book_id)

                if formats:
                    display_name = f"{title} — {author}"
                    books.append(Book(display_name, book_id, book_url, formats))

            return books if books else None

        except Exception as e:
            print(f"Ошибка поиска: {e}")
            return None

    def _get_available_formats(self, book_url: str):
        """Ищем прямые ссылки на FB2 и PDF на странице книги"""
        try:
            response = self.session.get(book_url)
            soup = BeautifulSoup(response.text, 'html.parser')

            formats = {}
            for link in soup.find_all('a', href=True):
                href = link.get('href', '')
                full = self.base_url + href if href.startswith('/') else href
                if '.pdf' in href.lower():
                    formats['pdf'] = full
                elif '.fb2' in href.lower():
                    formats['fb2'] = full
            return formats if formats else None

        except Exception as e:
            print(f"Ошибка получения форматов: {e}")
            return None

    def _get_formats_fallback(self, book_id: int):
        """Стандартный URL FB2 напрямую"""
        return {'fb2': f"{self.base_url}/b/{book_id}/fb2"}

    def _resolve_download_from_html(self, html: str):
        """Парсит HTML и ищет реальную ссылку на FB2"""
        soup = BeautifulSoup(html, 'html.parser')

        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            if href.lower().endswith('.fb2'):
                return href if href.startswith('http') else self.base_url + href

        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            text = link.get_text(strip=True).lower()
            if 'download' in href.lower() or 'скачать' in text:
                if not href.startswith('http'):
                    href = self.base_url + href
                if self.base_url in href:
                    return href

        meta = soup.find('meta', attrs={'http-equiv': 'refresh'})
        if meta:
            content = meta.get('content', '')
            if 'url=' in content.lower():
                url = content.split('url=')[-1].strip()
                return url if url.startswith('http') else self.base_url + url

        return None

    def download_book(self, book: Book, format_type: str = None):
        """Скачиваем FB2 (распаковываем ZIP если нужно)"""
        if not book.format_type or 'fb2' not in book.format_type:
            return None

        download_url = book.format_type['fb2']

        try:
            response = self.session.get(download_url)
            response.raise_for_status()

            content_type = response.headers.get('content-type', '').lower()
            if 'text/html' in content_type:
                real_url = self._resolve_download_from_html(response.text)
                if real_url:
                    response = self.session.get(real_url)
                    response.raise_for_status()
                else:
                    return None

            with tempfile.NamedTemporaryFile(delete=False, suffix='.fb2') as tmp_file:
                tmp_file.write(response.content)
                tmp_path = tmp_file.name

            is_zip = 'zip' in content_type or response.content[:2] == b'PK'
            fb2_path = tmp_path
            if is_zip:
                try:
                    with zipfile.ZipFile(tmp_path, 'r') as zf:
                        fb2_members = [m for m in zf.namelist() if m.lower().endswith('.fb2')]
                        if fb2_members:
                            fb2_path = zf.extract(fb2_members[0], tempfile.gettempdir())
                except Exception:
                    pass

            downloads_dir = Path.home() / "Downloads"
            downloads_dir.mkdir(exist_ok=True)
            safe_filename = re.sub(r'[<>":/\\|?*]', '_', book.name)[:100]
            final_filename = downloads_dir / f"{safe_filename}.fb2"
            shutil.move(fb2_path, final_filename)
            return str(final_filename)

        except Exception as e:
            print(f"Ошибка скачивания: {e}")
            return None

    def close(self):
        """Закрытие сессии"""
        self.session.close()