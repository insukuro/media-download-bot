# src/capabilities/vk_capability.py
from vkbottle.bot import BotLabeler, Message
from loguru import logger
import json

from .base import BaseCapability
from ..core.downloader.interfaces import Quality, MediaType, DownloadStatus
from ..adapters.vk.keyboards import VKKeyboard, VKButton
from ..config import settings


class VKCapability(BaseCapability):
    """
    VK-специфичная бизнес-логика.
    Адаптирует общую логику под особенности VK API.
    """
    
    def register_handlers(self, labeler: BotLabeler):
        """Регистрирует обработчики в VK лейблере"""
        
        @labeler.message(text=["/start", "начать", "Start"])
        async def cmd_start(message: Message):
            locale = self._get_locale(message)
            await self.messenger.send_message(
                chat_id=message.peer_id,
                text=self._t("welcome_message", locale) + "\n\n" + self._t("help_message", locale)
            )
        
        @labeler.message(text=["/help", "помощь", "Help"])
        async def cmd_help(message: Message):
            locale = self._get_locale(message)
            await self.messenger.send_message(
                chat_id=message.peer_id,
                text=self._t("help_message", locale)
            )
        
        @labeler.message(text=["/yt", "/youtube"])
        async def cmd_youtube(message: Message):
            url = self._extract_url(message.text, ["/yt", "/youtube"])
            if not url:
                locale = self._get_locale(message)
                await self.messenger.send_message(
                    chat_id=message.peer_id,
                    text=self._t("yt_usage", locale)
                )
                return
            
            await self.process_url_command(
                url=url,
                chat_id=message.peer_id,
                user_id=str(message.from_id),
                locale=self._get_locale(message),
                source_type="youtube"
            )
        
        @labeler.message(text=["/tt", "/tiktok"])
        async def cmd_tiktok(message: Message):
            url = self._extract_url(message.text, ["/tt", "/tiktok"])
            if not url:
                locale = self._get_locale(message)
                await self.messenger.send_message(
                    chat_id=message.peer_id,
                    text=self._t("tt_usage", locale)
                )
                return
            
            await self.process_url_command(
                url=url,
                chat_id=message.peer_id,
                user_id=str(message.from_id),
                locale=self._get_locale(message),
                source_type="tiktok"
            )
        
        @labeler.message(text=["/music"])
        async def cmd_music(message: Message):
            url = self._extract_url(message.text, ["/music"])
            if not url:
                locale = self._get_locale(message)
                await self.messenger.send_message(
                    chat_id=message.peer_id,
                    text=self._t("music_usage", locale)
                )
                return
            
            await self.process_music_command(
                url=url,
                chat_id=message.peer_id,
                user_id=str(message.from_id),
                locale=self._get_locale(message)
            )
        
        # Обработчик callback'ов от клавиатуры
        @labeler.raw_event("message_event")
        async def handle_callback(event: dict):
            if event["type"] == "message_event":
                payload = json.loads(event["object"]["payload"])
                callback_data = payload.get("callback", "")
                
                if callback_data.startswith("dl:"):
                    # Отвечаем на callback
                    await self.messenger.answer_callback(
                        event_id=event["object"]["event_id"],
                        user_id=event["object"]["user_id"],
                        peer_id=event["object"]["peer_id"]
                    )
                    
                    await self.process_download_callback(
                        callback_data=callback_data,
                        chat_id=event["object"]["peer_id"],
                        user_id=str(event["object"]["user_id"]),
                        locale=self._get_locale_from_event(event)
                    )
    
    # src/capabilities/vk_capability.py
    def build_quality_keyboard(self, url_key: str, available_qualities: list, cached_qualities: list = None):
        if cached_qualities is None:
            cached_qualities = []
        
        buttons = []
        
        video_qualities = [q for q in available_qualities 
                        if q in [Quality.LOW, Quality.MEDIUM, Quality.HIGH]]
        video_row = []
        for quality in video_qualities:
            prefix = "✅ " if quality in cached_qualities else ""
            video_row.append(
                VKButton.callback(
                    text=f"{prefix}📹 {quality.value}",
                    callback_data=f"dl:{url_key}:{quality.value}:video",
                    color="primary"
                )
            )
        if video_row:
            buttons.append(video_row)
        
        audio_qualities = [q for q in available_qualities 
                        if q in [Quality.AUDIO_LOW, Quality.AUDIO_MEDIUM, Quality.AUDIO_HIGH]]
        audio_row = []
        for quality in audio_qualities:
            prefix = "✅ " if quality in cached_qualities else ""
            audio_row.append(
                VKButton.callback(
                    text=f"{prefix}🎵 {quality.value}",
                    callback_data=f"dl:{url_key}:{quality.value}:audio",
                    color="positive"
                )
            )
        if audio_row:
            buttons.append(audio_row)
        
        return VKKeyboard.create_inline(buttons)


    async def send_metadata_response(self, chat_id: int, text: str, keyboard, 
                                   thumbnail_url: str, status_msg_id: int):
        """VK-специфичная отправка метаданных"""
        # VK не поддерживает HTML в сообщениях, очищаем теги
        clean_text = text.replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", "")
        
        await self.messenger.send_message(
            chat_id=chat_id,
            text=clean_text,
            reply_markup=keyboard
        )
    
    async def send_audio_result(self, chat_id: int, result, locale: str, status_msg_id: int):
        """VK-специфичная отправка аудио"""
        await self.messenger.send_media(
            chat_id=chat_id,
            media_type="audio",
            file_path=result.file_path,
            caption=f"✅ {result.metadata.title}\n👤 {result.metadata.author}"
        )
    
    async def send_download_result(self, chat_id: int, result, quality: Quality, locale: str):
        """VK-специфичная отправка результата загрузки"""
        caption = (
            f"✅ {result.metadata.title}\n"
            f"👤 {result.metadata.author}\n"
            f"📦 {result.metadata.size_mb:.1f} MB\n"
            f"🎬 {quality.value}"
        )
        
        await self.messenger.send_media(
            chat_id=chat_id,
            media_type=result.metadata.media_type.value,
            file_path=result.file_path,
            caption=caption
        )
    
    async def send_download_started(self, chat_id: int, quality: Quality, locale: str):
        """VK-специфичное сообщение о начале загрузки"""
        await self.messenger.send_message(
            chat_id=chat_id,
            text=f"⏳ Начинаю загрузку в качестве {quality.value}..."
        )
    
    def _extract_url(self, text: str, commands: list) -> str:
        """Извлекает URL из текста команды"""
        for cmd in commands:
            text = text.replace(cmd, "").strip()
        return text if text else None
    
    def _get_locale(self, message: Message) -> str:
        """Получить локаль пользователя"""
        return settings.default_locale
    
    def _get_locale_from_event(self, event: dict) -> str:
        """Получить локаль из event'а"""
        return settings.default_locale