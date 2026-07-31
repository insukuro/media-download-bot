# src/adapters/vk/adapter.py
from typing import Optional, Callable, Awaitable, Union
from vkbottle import Bot, API
from vkbottle.bot import Message, BotLabeler
from vkbottle.tools import PhotoMessageUploader, VideoUploader, AudioUploader, DocUploader
from loguru import logger
import aiohttp
import os

from ..base import MessengerAdapter
from ...config import settings


class VKAdapter(MessengerAdapter):
    """Адаптер VK - отвечает только за отправку/получение сообщений"""
    
    def __init__(self):
        self.api = API(token=settings.vk_token)
        self.bot = Bot(
            api=self.api,
            group_id=settings.vk_group_id,
        )
        self.labeler = BotLabeler()
        self.bot.labeler = self.labeler
        
        # Загрузчики медиа
        self._photo_uploader = PhotoMessageUploader(self.api)
        self._video_uploader = None  # Ленивая инициализация
        self._audio_uploader = None
        self._doc_uploader = None
        
        self._handlers_registered = False
        
        logger.info("VK adapter initialized")
    
    async def _get_video_uploader(self):
        if not self._video_uploader:
            self._video_uploader = VideoUploader(self.api)
        return self._video_uploader
    
    async def _get_audio_uploader(self):
        if not self._audio_uploader:
            self._audio_uploader = AudioUploader(self.api)
        return self._audio_uploader
    
    async def _get_doc_uploader(self):
        if not self._doc_uploader:
            self._doc_uploader = DocUploader(self.api)
        return self._doc_uploader
    
    def register_handlers(self, handler_registrar: Callable[[BotLabeler], Awaitable[None]]):
        """Регистрирует обработчики из capability слоя"""
        handler_registrar(self.labeler)
        self._handlers_registered = True
    
    async def start(self):
        """Запуск бота"""
        if not self._handlers_registered:
            raise RuntimeError("Handlers not registered. Call register_handlers() first")
        
        logger.info("Starting VK bot...")
        await self.bot.run_polling()
    
    async def stop(self):
        """Остановка бота"""
        logger.info("Stopping VK bot...")
        await self.api.http_client.close()
    
    async def send_message(
        self,
        chat_id: int,
        text: str,
        reply_markup=None,
        parse_mode: str = "HTML"
    ):
        """Отправить текстовое сообщение"""
        # VK использует peer_id как chat_id
        await self.api.messages.send(
            peer_id=chat_id,
            message=text,
            keyboard=reply_markup,
            random_id=0
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
        try:
            if media_type == "video":
                uploader = await self._get_video_uploader()
                attachment = await uploader.upload(
                    file_source=file_path,
                    name=os.path.basename(file_path),
                    is_private=False
                )
            elif media_type == "audio":
                uploader = await self._get_audio_uploader()
                attachment = await uploader.upload(
                    file_source=file_path,
                    artist="MediaBot",
                    title=os.path.basename(file_path)
                )
            elif media_type == "document":
                uploader = await self._get_doc_uploader()
                attachment = await uploader.upload(
                    file_source=file_path,
                    title=os.path.basename(file_path)
                )
            elif media_type == "photo":
                attachment = await self._photo_uploader.upload(
                    file_source=file_path
                )
            else:
                raise ValueError(f"Unsupported media type: {media_type}")
            
            # Отправляем с вложением
            await self.api.messages.send(
                peer_id=chat_id,
                message=caption or "",
                attachment=attachment,
                random_id=0
            )
            
            return attachment
            
        except Exception as e:
            logger.error(f"Failed to send media to VK: {e}")
            # Fallback: отправляем ссылкой
            await self.send_message(
                chat_id=chat_id,
                text=f"❌ Не удалось отправить медиа: {str(e)}"
            )
    
    async def send_photo(
        self,
        chat_id: int,
        photo_path: str,
        caption: Optional[str] = None
    ):
        """Отправить фото"""
        return await self.send_media(
            chat_id=chat_id,
            media_type="photo",
            file_path=photo_path,
            caption=caption
        )
    
    async def answer_callback(self, event_id: str, user_id: int, peer_id: int):
        """Ответить на callback (VK использует события)"""
        await self.api.messages.send_message_event_answer(
            event_id=event_id,
            user_id=user_id,
            peer_id=peer_id,
            event_data={"type": "show_snackbar", "text": "Обрабатываю..."}
        )
    
    async def edit_message(
        self, 
        peer_id: int, 
        message_id: int, 
        text: str,
        reply_markup=None
    ):
        """Редактировать сообщение"""
        await self.api.messages.edit(
            peer_id=peer_id,
            message_id=message_id,
            message=text,
            keyboard=reply_markup
        )
    
    async def delete_message(self, peer_id: int, message_ids: list):
        """Удалить сообщения"""
        await self.api.messages.delete(
            peer_id=peer_id,
            message_ids=message_ids,
            delete_for_all=True
        )
    
    async def get_user_info(self, user_id: int) -> dict:
        """Получить информацию о пользователе"""
        users = await self.api.users.get(user_ids=[user_id])
        return users[0] if users else {}