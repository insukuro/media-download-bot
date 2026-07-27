# src/main.py
import asyncio
import sys
from loguru import logger

from src.config import settings
from src.database import init_db
from src.core.downloader import DownloadService
from src.core.cache import FileCacheManager
from src.core.queue import AsyncDownloadQueue
from src.sources import YouTubeDownloader, TikTokDownloader
from src.adapters.telegram import TelegramAdapter


async def main():
    """Точка входа"""
    
    # Настройка логирования
    logger.remove()
    logger.add(
        sys.stdout,
        level=settings.log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
    )
    logger.add(
        "logs/app_{time:YYYY-MM-DD}.log",
        rotation="1 day",
        retention="7 days",
        level="DEBUG"
    )
    
    logger.info(f"Starting {settings.app_name}...")
    
    # Инициализация БД
    await init_db()
    logger.info("Database initialized")
    
    # Инициализация компонентов
    cache = FileCacheManager()
    queue = AsyncDownloadQueue()
    
    # Регистрация источников
    sources = {}
    if settings.youtube_enabled:
        sources["youtube"] = YouTubeDownloader()
        logger.info("YouTube source registered")
    if settings.tiktok_enabled:
        sources["tiktok"] = TikTokDownloader()
        logger.info("TikTok source registered")
    
    # Сервис загрузки
    download_service = DownloadService(sources, cache, queue)
    
    # Запуск адаптеров
    if settings.telegram_token:
        telegram = TelegramAdapter(download_service)
        logger.info("Telegram adapter initialized")
        await telegram.start()
    else:
        logger.warning("Telegram token not configured")
    
    # Держим приложение запущенным
    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutting down...")


if __name__ == "__main__":
    asyncio.run(main())