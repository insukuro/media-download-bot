# src/adapters/telegram/adapter.py
from typing import Optional, Callable, Awaitable
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from loguru import logger

from ..base import MessengerAdapter
from ...config import settings


class TelegramAdapter(MessengerAdapter):
    """Адаптер Telegram - отвечает только за отправку/получение сообщений"""
    
    def __init__(self):
        self.bot = Bot(
            token=settings.telegram_token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )
        self.dp = Dispatcher()
        self._handlers_registered = False
        
        logger.info("Telegram adapter initialized")
    
    def register_handlers(self, handler_registrar: Callable[[Dispatcher], Awaitable[None]]):
        """Регистрирует обработчики из capability слоя"""
        handler_registrar(self.dp)
        self._handlers_registered = True
    
    async def start(self):
        """Запуск бота"""
        if not self._handlers_registered:
            raise RuntimeError("Handlers not registered. Call register_handlers() first")
        
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
        """Отправить медиафайл с проверкой размера"""
        
        # Проверяем размер файла
        file_size = os.path.getsize(file_path)
        max_size = 50 * 1024 * 1024  # 50MB для Telegram ботов
        
        if file_size > max_size:
            # Если файл слишком большой, отправляем как документ
            logger.warning(f"File too large for {media_type}: {file_size / (1024*1024):.1f}MB, sending as document")
            return await self.send_large_file(chat_id, file_path, caption)
        
        try:
            input_file = FSInputFile(file_path)
            
            if media_type == "video":
                await self.bot.send_video(
                    chat_id=chat_id,
                    video=input_file,
                    caption=caption,
                    thumb=FSInputFile(thumbnail) if thumbnail else None,
                    supports_streaming=True
                )
            elif media_type == "audio":
                await self.bot.send_audio(
                    chat_id=chat_id,
                    audio=input_file,
                    caption=caption
                )
            elif media_type == "document":
                await self.bot.send_document(
                    chat_id=chat_id,
                    document=input_file,
                    caption=caption
                )
            
        except TelegramEntityTooLarge:
            # Fallback: отправляем как документ
            logger.warning(f"Entity too large, sending as document")
            await self.send_large_file(chat_id, file_path, caption)
        except Exception as e:
            logger.error(f"Failed to send media: {e}")
            await self.send_message(
                chat_id=chat_id,
                text=f"❌ Ошибка отправки файла: {str(e)}"
            )
    
    async def send_large_file(self, chat_id: int, file_path: str, caption: Optional[str] = None):
        """Отправка большого файла как документа"""
        try:
            input_file = FSInputFile(file_path)
            await self.bot.send_document(
                chat_id=chat_id,
                document=input_file,
                caption=caption
            )
        except Exception as e:
            logger.error(f"Failed to send large file: {e}")
            await self.send_message(
                chat_id=chat_id,
                text=f"❌ Файл слишком большой для отправки ({os.path.getsize(file_path) / (1024*1024):.1f}MB)"
            )
    
    async def send_photo(
        self,
        chat_id: int,
        photo_path: str,
        caption: Optional[str] = None
    ):
        """Отправить фото (поддерживает URL и локальные файлы)"""
        try:
            # Проверяем, URL это или локальный файл
            if photo_path.startswith(('http://', 'https://')):
                # Для URL используем URLInputFile
                try:
                    photo = URLInputFile(photo_path)
                    await self.bot.send_photo(
                        chat_id=chat_id,
                        photo=photo,
                        caption=caption
                    )
                except TelegramBadRequest as e:
                    logger.warning(f"Failed to send photo by URL: {e}, downloading...")
                    # Fallback: скачиваем и отправляем как файл
                    await self._send_photo_as_file(chat_id, photo_path, caption)
            else:
                # Локальный файл
                photo = FSInputFile(photo_path)
                await self.bot.send_photo(
                    chat_id=chat_id,
                    photo=photo,
                    caption=caption
                )
        except Exception as e:
            logger.error(f"Failed to send photo: {e}")
            # Последний fallback - отправляем только текст
            if caption:
                await self.send_message(chat_id=chat_id, text=caption)
    
    async def _send_photo_as_file(self, chat_id: int, url: str, caption: Optional[str] = None):
        """Скачивает фото по URL и отправляет как файл"""
        temp_file = None
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=30) as response:
                    if response.status == 200:
                        # Сохраняем во временный файл
                        with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as tmp:
                            temp_file = tmp.name
                            async for chunk in response.content.iter_chunked(8192):
                                tmp.write(chunk)
                        
                        # Отправляем как фото
                        photo = FSInputFile(temp_file)
                        await self.bot.send_photo(
                            chat_id=chat_id,
                            photo=photo,
                            caption=caption
                        )
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
        """Ответить на callback query"""
        await self.bot.answer_callback_query(callback_query_id)
    
    async def edit_message_caption(
        self, 
        chat_id: int, 
        message_id: int, 
        caption: str, 
        reply_markup=None
    ):
        """Изменить подпись сообщения"""
        await self.bot.edit_message_caption(
            chat_id=chat_id,
            message_id=message_id,
            caption=caption,
            reply_markup=reply_markup
        )
    
    async def delete_message(self, chat_id: int, message_id: int):
        """Удалить сообщение"""
        await self.bot.delete_message(chat_id=chat_id, message_id=message_id)