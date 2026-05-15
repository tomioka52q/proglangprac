import aiohttp

API_URL = "https://api.remanga.org/api"


class RemangaParser:
    def __init__(self):
        self.session = None
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

    async def _get_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                headers=self.headers,
                connector=aiohttp.TCPConnector(ssl=False)
            )
        return self.session

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()

    async def search(self, query):
        url = f"{API_URL}/search/"
        try:
            session = await self._get_session()
            async with session.get(url, params={"query": query}) as resp:
                print(f"[INFO] status={resp.status}, query={query!r}")
                if resp.status != 200:
                    print(f"[INFO] bad status, returning []")
                    return []
                data = await resp.json()
                results = []
                content = data.get("content", [])
                print(f"[INFO] results count={len(content)}")
                for item in content:
                    title = item.get("rus_name") or item.get("en_name", "Unknown")
                    results.append({
                        "id": item.get("dir", ""),
                        "title": title,
                        "cover_url": f"https://remanga.org{item.get('img', {}).get('high')}" if item.get("img", {}).get("high") else None,
                        "year": item.get("issue_year"),
                        "status": item.get("status", {}).get("name") if isinstance(item.get("status"), dict) else None,
                        "chapters_count": item.get("count_chapters", 0)
                    })
                return results
        except Exception as e:
            print(f"[DEBUG search] exception: {e}")
            return []

    async def get_title(self, manga_id):
        url = f"{API_URL}/titles/{manga_id}/"
        try:
            session = await self._get_session()
            async with session.get(url) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                item = data.get("content", {})
                return {
                    "id": item.get("dir", manga_id),
                    "title": item.get("rus_name") or item.get("en_name", "Unknown"),
                    "cover_url": f"https://remanga.org{item.get('img', {}).get('high')}" if item.get("img", {}).get("high") else None,
                    "description": item.get("description"),
                    "year": item.get("issue_year"),
                    "status": item.get("status", {}).get("name") if isinstance(item.get("status"), dict) else None,
                    "chapters_count": item.get("count_chapters", 0)
                }
        except Exception:
            return None

    async def get_chapters(self, manga_id):
        url = f"{API_URL}/titles/{manga_id}/"
        try:
            session = await self._get_session()
            async with session.get(url) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
                branches = data.get("content", {}).get("branches", [])
                if not branches:
                    return []
                branch_id = branches[0]["id"]

            all_chapters = []
            page = 1
            while True:
                chapters_url = f"{API_URL}/titles/chapters/"
                params = {"branch_id": branch_id, "ordering": "index", "page": page, "count": 100}
                async with session.get(chapters_url, params=params) as resp:
                    if resp.status != 200:
                        break
                    ch_data = await resp.json()
                    content = ch_data.get("content", [])
                    if not content:
                        break
                    for item in content:
                        all_chapters.append({
                            "id": str(item.get("id", "")),
                            "number": float(item.get("chapter", 0)),
                            "volume": item.get("tome"),
                            "name": item.get("name"),
                            "pages_count": item.get("pages", 0)
                        })
                    if len(content) < 100:
                        break
                    page += 1
            return all_chapters
        except Exception:
            return []

    async def get_chapter_pages(self, chapter_id):
        url = f"{API_URL}/titles/chapters/{chapter_id}/"
        try:
            session = await self._get_session()
            async with session.get(url) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
                page_list = data.get("content", {}).get("pages", [])
                pages = []
                for idx, page in enumerate(page_list, start=1):
                    image_url = ""
                    if isinstance(page, str):
                        image_url = page
                    elif isinstance(page, list) and len(page) > 0:
                        first = page[0]
                        image_url = first.get("link", "") if isinstance(first, dict) else first
                    elif isinstance(page, dict):
                        image_url = page.get("link") or page.get("url") or page.get("image", "")
                    if image_url:
                        if not image_url.startswith("http"):
                            image_url = f"https://remanga.org{image_url}"
                        pages.append({"number": idx, "image_url": image_url.strip()})
                return pages
        except Exception:
            return []

    async def download_image(self, url):
        import asyncio
        await asyncio.sleep(0.3)
        try:
            session = await self._get_session()
            async with session.get(url, headers={"Referer": "https://remanga.org/"}) as resp:
                if resp.status == 200:
                    return await resp.read()
                raise Exception(f"Status {resp.status}")
        except Exception as e:
            raise Exception(f"Download failed: {e}")
