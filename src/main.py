# src/main.py
import asyncio
import sys
import os
from loguru import logger

from src.config import settings
from src.database import init_db
from src.core.downloader import DownloadService
from src.core.cache import FileCacheManager
from src.core.cache.file_id_cache import FileIdCache
from src.core.queue import AsyncDownloadQueue
from src.sources import YouTubeDownloader, TikTokDownloader
from src.adapters.telegram.adapter import TelegramAdapter
from src.capabilities.telegram_capability import TelegramCapability
from src.core.url_storage import UrlStorage


async def main():
    # Создаём рабочие директории
    for dir_name in [settings.temp_dir, settings.cache_dir, "logs", "data"]:
        path = os.path.join(settings.base_dir, dir_name)
        os.makedirs(path, exist_ok=True)

    logger.remove()
    logger.add(sys.stdout, level=settings.log_level,
               format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | "
                      "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>")

    logger.info(f"Starting {settings.app_name}...")
    await init_db()

    cache = FileCacheManager()
    queue = AsyncDownloadQueue()

    sources = {}
    if settings.youtube_enabled:
        sources["youtube"] = YouTubeDownloader()
    if settings.tiktok_enabled:
        sources["tiktok"] = TikTokDownloader()

    download_service = DownloadService(sources, cache, queue)
    await download_service.start()

    url_storage = UrlStorage()
    url_storage.cleanup(max_age_hours=24)

    file_id_cache = FileIdCache()

    adapters = []

    if settings.telegram_token:
        telegram = TelegramAdapter(file_id_cache=file_id_cache)
        telegram_capability = TelegramCapability(
            download_service=download_service,
            messenger=telegram,
            url_storage=url_storage
        )
        telegram.register_handlers(telegram_capability.register_handlers)
        adapters.append(telegram.start())
        logger.info("✅ Telegram adapter configured")

    if not adapters:
        logger.error("❌ No adapters configured!")
        return

    try:
        await asyncio.gather(*adapters)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutting down...")
        await download_service.stop()


if __name__ == "__main__":
    asyncio.run(main())