from typing import Optional
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from loguru import logger

from ..base import MessengerAdapter
from .handlers import register_handlers
from ...core.downloader.service import DownloadService
from ...config import settings


class TelegramAdapter(MessengerAdapter):
    """Адаптер Telegram"""
    
    def __init__(self, download_service: DownloadService):
        self.bot = Bot(
            token=settings.telegram_token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )
        self.dp = Dispatcher()
        self.download_service = download_service
        
        # Регистрируем обработчики
        register_handlers(self.dp, download_service)
        
        logger.info("Telegram adapter initialized")
    
    async def start(self):
        """Запуск бота"""
        logger.info("Starting Telegram bot...")
        await self.dp.start_polling(self.bot)
    
    async def stop(self):
        """Остановка бота"""
        logger.info("Stopping Telegram bot...")
        await self.bot.session.close()
    
    async def send_message(
        self,
        chat_id: int,
        text: str,
        reply_markup=None,
        parse_mode: str = "HTML"
    ):
        """Отправить текстовое сообщение"""
        await self.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode
        )
    
    async def send_media(
        self,
        chat_id: int,
        media_type: str,
        file_path: str,
        caption: Optional[str] = None,
        thumbnail: Optional[str] = None
    ):
        """Отправить медиафайл"""
        if media_type == "video":
            await self.bot.send_video(
                chat_id=chat_id,
                video=open(file_path, 'rb'),
                caption=caption,
                thumb=open(thumbnail, 'rb') if thumbnail else None
            )
        elif media_type == "audio":
            await self.bot.send_audio(
                chat_id=chat_id,
                audio=open(file_path, 'rb'),
                caption=caption
            )
        elif media_type == "document":
            await self.bot.send_document(
                chat_id=chat_id,
                document=open(file_path, 'rb'),
                caption=caption
            )
    
    async def send_photo(
        self,
        chat_id: int,
        photo_path: str,
        caption: Optional[str] = None
    ):
        """Отправить фото"""
        await self.bot.send_photo(
            chat_id=chat_id,
            photo=open(photo_path, 'rb'),
            caption=caption
        )