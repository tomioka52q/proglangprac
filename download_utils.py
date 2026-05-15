import os

import aiofiles
import img2pdf
from PIL import Image

DOWNLOADS_DIR = "downloads"
os.makedirs(DOWNLOADS_DIR, exist_ok=True)


async def save_temp_file(content, filename):
    filepath = os.path.join(DOWNLOADS_DIR, filename)
    async with aiofiles.open(filepath, "wb") as f:
        await f.write(content)
    return filepath


async def images_to_pdf(image_paths, output_filename):
    output_path = os.path.join(DOWNLOADS_DIR, output_filename)
    with open(output_path, "wb") as f:
        f.write(img2pdf.convert(image_paths))
    return output_path


async def compress_image(image_path, quality=70):
    output_path = image_path.replace(".jpg", "_compressed.jpg")
    with Image.open(image_path) as img:
        if max(img.size) > 2000:
            img.thumbnail((2000, 2000), Image.Resampling.LANCZOS)
        img.save(output_path, "JPEG", quality=quality, optimize=True)
    return output_path


async def cleanup_files(filepaths):
    for path in filepaths:
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass


async def download_chapter(chapter_id, manga_title, chapter_num, remanga_parser, progress_callback=None):
    pages = await remanga_parser.get_chapter_pages(chapter_id)
    if not pages:
        raise Exception("Нет страниц")

    temp_images = []
    total = len(pages)
    for idx, page in enumerate(pages, 1):
        if progress_callback:
            await progress_callback(idx, total, "downloading")
        img_data = await remanga_parser.download_image(page["image_url"])
        path = await save_temp_file(img_data, f"page_{page['number']}.jpg")
        temp_images.append(path)

    if progress_callback:
        await progress_callback(total, total, "creating_pdf")

    safe = "".join(c for c in manga_title if c.isalnum() or c in (" ", "-", "_")).strip()[:50]
    filename = f"{safe} - Глава {chapter_num}.pdf"
    pdf_path = await images_to_pdf(temp_images, filename)

    size = os.path.getsize(pdf_path)
    if size > 50 * 1024 * 1024:
        await cleanup_files(temp_images + [pdf_path])
        return await download_chapter_compressed(chapter_id, manga_title, chapter_num, remanga_parser, progress_callback)

    await cleanup_files(temp_images)
    return pdf_path


async def download_chapter_compressed(chapter_id, manga_title, chapter_num, remanga_parser, progress_callback=None):
    pages = await remanga_parser.get_chapter_pages(chapter_id)
    temp_images = []
    total = len(pages)
    for idx, page in enumerate(pages, 1):
        if progress_callback:
            await progress_callback(idx, total, "downloading")
        img_data = await remanga_parser.download_image(page["image_url"])
        path = await save_temp_file(img_data, f"page_{page['number']}.jpg")
        compressed = await compress_image(path)
        temp_images.append(compressed)

    if progress_callback:
        await progress_callback(total, total, "creating_pdf")

    safe = "".join(c for c in manga_title if c.isalnum() or c in (" ", "-", "_")).strip()[:50]
    filename = f"{safe} - Глава {chapter_num}.pdf"
    pdf_path = await images_to_pdf(temp_images, filename)
    await cleanup_files(temp_images)
    return pdf_path
