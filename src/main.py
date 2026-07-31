
import asyncio
import sys
from loguru import logger

from src.config import settings
from src.database import init_db
from src.core.downloader import DownloadService
from src.core.cache import FileCacheManager
from src.core.queue import AsyncDownloadQueue
from src.sources import YouTubeDownloader, TikTokDownloader
from src.adapters.telegram.adapter import TelegramAdapter
from src.adapters.vk.adapter import VKAdapter
from src.capabilities.telegram_capability import TelegramCapability
from src.capabilities.vk_capability import VKCapability
from src.core.url_storage import UrlStorage

async def main():
    """Точка входа"""
    import os
    # Настройка логирования
    logger.remove()
    logger.add(
        sys.stdout,
        level=settings.log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
    )
    
    logger.info(f"Starting {settings.app_name}...")
    
    # Инициализация БД
    await init_db()
    
    # Общие компоненты
    cache = FileCacheManager()
    queue = AsyncDownloadQueue()
    
    # Источники контента
    sources = {}
    if settings.youtube_enabled:
        sources["youtube"] = YouTubeDownloader()
    if settings.tiktok_enabled:
        sources["tiktok"] = TikTokDownloader()
    
    # Сервис загрузки с worker pool
    download_service = DownloadService(sources, cache, queue)
    await download_service.start()
    
    # Общее хранилище URL
    url_storage = UrlStorage()
    url_storage.cleanup(max_age_hours=24)  # очищаем при старте
    
    adapters = []
    
    if settings.telegram_token:
        telegram = TelegramAdapter()
        telegram_capability = TelegramCapability(
            download_service=download_service,
            messenger=telegram,
            url_storage=url_storage
        )
        telegram.register_handlers(telegram_capability.register_handlers)
        adapters.append(telegram.start())
        logger.info("✅ Telegram adapter configured")
    
    if settings.vk_token:
        vk = VKAdapter()
        vk_capability = VKCapability(
            download_service=download_service,
            messenger=vk,
            url_storage=url_storage
        )
        vk.register_handlers(vk_capability.register_handlers)
        adapters.append(vk.start())
        logger.info("✅ VK adapter configured")
    
    if not adapters:
        logger.error("❌ No adapters configured! Add TELEGRAM_TOKEN or VK_TOKEN to .env")
        return
    
    try:
        await asyncio.gather(*adapters)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutting down...")
        await download_service.stop()


if __name__ == "__main__":
    asyncio.run(main())