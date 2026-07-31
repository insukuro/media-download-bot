# src/adapters/telegram/adapter.py
import os
import aiohttp
import tempfile
from typing import Optional, Callable, Awaitable
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import FSInputFile, URLInputFile
from aiogram.exceptions import TelegramBadRequest, TelegramEntityTooLarge
from loguru import logger

from ..base import MessengerAdapter
from ...config import settings


class TelegramAdapter(MessengerAdapter):
    """Адаптер Telegram - отвечает только за отправку/получение сообщений"""

    def __init__(self, file_id_cache: 'FileIdCache' = None):
        self.bot = Bot(
            token=settings.telegram_token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )
        self.dp = Dispatcher()
        self.file_id_cache = file_id_cache
        self._handlers_registered = False
        logger.info("Telegram adapter initialized")

    def register_handlers(self, handler_registrar: Callable[[Dispatcher], Awaitable[None]]):
        handler_registrar(self.dp)
        self._handlers_registered = True

    async def start(self):
        if not self._handlers_registered:
            raise RuntimeError("Handlers not registered. Call register_handlers() first")
        logger.info("Starting Telegram bot...")
        await self.dp.start_polling(self.bot)

    async def stop(self):
        logger.info("Stopping Telegram bot...")
        await self.bot.session.close()

    async def send_message(
        self,
        chat_id: int,
        text: str,
        reply_markup=None,
        parse_mode: str = "HTML"
    ):
        """Отправить текстовое сообщение и вернуть его ID"""
        msg = await self.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode
        )
        return msg.message_id

    async def send_media(
        self,
        chat_id: int,
        media_type: str,
        file_path: str,
        caption: Optional[str] = None,
        thumbnail: Optional[str] = None,
        url: str = None,
        quality: str = None
    ) -> Optional[str]:
        """Отправить медиафайл и вернуть file_id"""
        file_id = None

        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            await self.send_message(chat_id=chat_id, text="❌ Файл не найден")
            return None

        file_size = os.path.getsize(file_path)
        max_size = 50 * 1024 * 1024

        if file_size > max_size:
            logger.warning(f"File too large, sending as document")
            return await self._send_document_get_file_id(chat_id, file_path, caption)

        try:
            input_file = FSInputFile(file_path)

            if media_type == "video":
                msg = await self.bot.send_video(
                    chat_id=chat_id,
                    video=input_file,
                    caption=caption,
                    thumbnail=FSInputFile(thumbnail) if thumbnail else None,
                    supports_streaming=True
                )
                file_id = msg.video.file_id if msg.video else None
            elif media_type == "audio":
                msg = await self.bot.send_audio(
                    chat_id=chat_id,
                    audio=input_file,
                    caption=caption
                )
                file_id = msg.audio.file_id if msg.audio else None
            elif media_type == "document":
                msg = await self.bot.send_document(
                    chat_id=chat_id,
                    document=input_file,
                    caption=caption
                )
                file_id = msg.document.file_id if msg.document else None

            if file_id and self.file_id_cache and url and quality:
                from src.core.downloader.interfaces import Quality as Q
                await self.file_id_cache.set(url, Q(quality), file_id, media_type, caption)

            return file_id

        except TelegramEntityTooLarge:
            logger.warning("Entity too large, sending as document")
            return await self._send_document_get_file_id(chat_id, file_path, caption)
        except Exception as e:
            logger.error(f"Failed to send media: {e}")
            await self.send_message(chat_id=chat_id, text=f"❌ Ошибка отправки файла: {str(e)}")
            return None

    async def send_media_by_file_id(
        self,
        chat_id: int,
        file_id: str,
        media_type: str,
        caption: Optional[str] = None
    ):
        """Отправить медиа по file_id (мгновенно)"""
        try:
            if media_type == "video":
                await self.bot.send_video(chat_id=chat_id, video=file_id, caption=caption)
            elif media_type == "audio":
                await self.bot.send_audio(chat_id=chat_id, audio=file_id, caption=caption)
            elif media_type == "document":
                await self.bot.send_document(chat_id=chat_id, document=file_id, caption=caption)
        except Exception as e:
            logger.error(f"Failed to send by file_id: {e}")
            raise

    async def _send_document_get_file_id(self, chat_id: int, file_path: str, caption: str = None) -> Optional[str]:
        try:
            msg = await self.bot.send_document(
                chat_id=chat_id,
                document=FSInputFile(file_path),
                caption=caption
            )
            return msg.document.file_id if msg.document else None
        except Exception as e:
            logger.error(f"Failed to send document: {e}")
            return None

    async def send_photo(
        self,
        chat_id: int,
        photo_path: str,
        caption: Optional[str] = None
    ):
        try:
            if photo_path.startswith(('http://', 'https://')):
                try:
                    photo = URLInputFile(photo_path)
                    await self.bot.send_photo(chat_id=chat_id, photo=photo, caption=caption)
                except TelegramBadRequest:
                    logger.warning(f"Failed to send photo by URL, downloading...")
                    await self._send_photo_as_file(chat_id, photo_path, caption)
            else:
                photo = FSInputFile(photo_path)
                await self.bot.send_photo(chat_id=chat_id, photo=photo, caption=caption)
        except Exception as e:
            logger.error(f"Failed to send photo: {e}")
            if caption:
                await self.send_message(chat_id=chat_id, text=caption)

    async def _send_photo_as_file(self, chat_id: int, url: str, caption: Optional[str] = None):
        temp_file = None
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=30) as response:
                    if response.status == 200:
                        with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as tmp:
                            temp_file = tmp.name
                            async for chunk in response.content.iter_chunked(8192):
                                tmp.write(chunk)
                        photo = FSInputFile(temp_file)
                        await self.bot.send_photo(chat_id=chat_id, photo=photo, caption=caption)
                    else:
                        raise Exception(f"Failed to download photo: status {response.status}")
        except Exception as e:
            logger.error(f"Failed to send photo as file: {e}")
            if caption:
                await self.send_message(chat_id=chat_id, text=caption)
        finally:
            if temp_file and os.path.exists(temp_file):
                os.unlink(temp_file)

    async def answer_callback(self, callback_query_id: str):
        await self.bot.answer_callback_query(callback_query_id)

    async def edit_message_caption(self, chat_id: int, message_id: int, caption: str, reply_markup=None):
        await self.bot.edit_message_caption(
            chat_id=chat_id, message_id=message_id, caption=caption, reply_markup=reply_markup
        )

    async def delete_message(self, chat_id: int, message_id: int):
        if message_id is None:
            return
        try:
            await self.bot.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception as e:
            logger.debug(f"Failed to delete message {message_id}: {e}")