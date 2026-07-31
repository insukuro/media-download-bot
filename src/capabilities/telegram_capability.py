# src/capabilities/telegram_capability.py
from aiogram import Dispatcher, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from loguru import logger

from .base import BaseCapability
from ..core.downloader.interfaces import Quality, MediaType, DownloadStatus
from ..config import settings


class TelegramCapability(BaseCapability):
    """
    Telegram-специфичная бизнес-логика.
    Адаптирует общую логику под особенности Telegram API.
    """
    
    def register_handlers(self, dp: Dispatcher):
        """Регистрирует обработчики в Telegram диспетчере"""
        
        @dp.message(Command("start"))
        async def cmd_start(message: types.Message):
            locale = self._get_locale(message)
            await self.messenger.send_message(
                chat_id=message.chat.id,
                text=self._t("welcome_message", locale) + "\n\n" + self._t("help_message", locale)
            )
        
        @dp.message(Command("help"))
        async def cmd_help(message: types.Message):
            locale = self._get_locale(message)
            await self.messenger.send_message(
                chat_id=message.chat.id,
                text=self._t("help_message", locale)
            )
        
        @dp.message(Command("yt"))
        async def cmd_youtube(message: types.Message):
            locale = self._get_locale(message)
            
            args = message.text.split(maxsplit=1)
            if len(args) < 2:
                await self.messenger.send_message(
                    chat_id=message.chat.id,
                    text=self._t("yt_usage", locale)
                )
                return
            
            url = args[1].strip()
            await self.process_url_command(
                url=url,
                chat_id=message.chat.id,
                user_id=str(message.from_user.id),
                locale=locale,
                source_type="youtube"
            )
        
        @dp.message(Command("tt"))
        async def cmd_tiktok(message: types.Message):
            locale = self._get_locale(message)
            
            args = message.text.split(maxsplit=1)
            if len(args) < 2:
                await self.messenger.send_message(
                    chat_id=message.chat.id,
                    text=self._t("tt_usage", locale)
                )
                return
            
            url = args[1].strip()
            await self.process_url_command(
                url=url,
                chat_id=message.chat.id,
                user_id=str(message.from_user.id),
                locale=locale,
                source_type="tiktok"
            )
        
        @dp.message(Command("music"))
        async def cmd_music(message: types.Message):
            locale = self._get_locale(message)
            
            args = message.text.split(maxsplit=1)
            if len(args) < 2:
                await self.messenger.send_message(
                    chat_id=message.chat.id,
                    text=self._t("music_usage", locale)
                )
                return
            
            url = args[1].strip()
            await self.process_music_command(
                url=url,
                chat_id=message.chat.id,
                user_id=str(message.from_user.id),
                locale=locale
            )
        
        @dp.callback_query(lambda c: c.data.startswith("dl:"))
        async def process_download(callback_query: types.CallbackQuery):
            locale = self._get_locale(callback_query)
            
            # Отвечаем на callback
            await self.messenger.answer_callback(callback_query.id)
            
            # Обрабатываем загрузку
            await self.process_download_callback(
                callback_data=callback_query.data,
                chat_id=callback_query.message.chat.id,
                user_id=str(callback_query.from_user.id),
                locale=locale
            )
            
            # Удаляем сообщение с кнопками после загрузки
            await self.messenger.delete_message(
                chat_id=callback_query.message.chat.id,
                message_id=callback_query.message.message_id
            )
    
    def build_quality_keyboard(self, url_key: str, available_qualities: list):
        """Строит Telegram inline клавиатуру с качествами"""
        builder = InlineKeyboardBuilder()
        
        # Видео качества
        video_qualities = [q for q in available_qualities 
                         if q in [Quality.LOW, Quality.MEDIUM, Quality.HIGH]]
        for quality in video_qualities:
            builder.button(
                text=f"📹 {quality.value}",
                callback_data=f"dl:{url_key}:{quality.value}:video"
            )
        if video_qualities:
            builder.adjust(len(video_qualities))
        
        # Аудио качества
        audio_qualities = [q for q in available_qualities 
                         if q in [Quality.AUDIO_LOW, Quality.AUDIO_MEDIUM, Quality.AUDIO_HIGH]]
        for quality in audio_qualities:
            builder.button(
                text=f"🎵 {quality.value}",
                callback_data=f"dl:{url_key}:{quality.value}:audio"
            )
        if audio_qualities:
            builder.adjust(len(audio_qualities))
        
        return builder.as_markup()
    
    async def send_metadata_response(self, chat_id: int, text: str, keyboard, 
                                   thumbnail_url: str, status_msg_id: int):
        """Telegram-специфичная отправка метаданных с проверками"""
        try:
            if thumbnail_url and thumbnail_url.startswith(('http://', 'https://')):
                # Есть превью - отправляем фото с информацией
                try:
                    # Используем URLInputFile для URL
                    from aiogram.types import URLInputFile
                    photo = URLInputFile(thumbnail_url)
                    
                    await self.messenger.bot.send_photo(
                        chat_id=chat_id,
                        photo=photo,
                        caption=text,
                        reply_markup=keyboard  # Клавиатура прямо в сообщении с фото
                    )
                except Exception as e:
                    logger.warning(f"Failed to send thumbnail by URL, trying download: {e}")
                    # Пробуем скачать и отправить
                    await self.messenger.send_photo(
                        chat_id=chat_id,
                        photo_path=thumbnail_url,
                        caption=text
                    )
                    # Клавиатуру отдельно
                    await self.messenger.send_message(
                        chat_id=chat_id,
                        text="Выберите качество:",
                        reply_markup=keyboard
                    )
                
                # Удаляем статусное сообщение
                try:
                    await self.messenger.delete_message(chat_id, status_msg_id)
                except:
                    pass
            else:
                # Нет превью - просто текст с клавиатурой
                await self.messenger.send_message(
                    chat_id=chat_id,
                    text=text,
                    reply_markup=keyboard
                )
                # Удаляем статус
                try:
                    await self.messenger.delete_message(chat_id, status_msg_id)
                except:
                    pass
                    
        except Exception as e:
            logger.error(f"Failed to send metadata response: {e}")
            # Fallback: просто текст с клавиатурой
            await self.messenger.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=keyboard
            )
    
    async def send_audio_result(self, chat_id: int, result, locale: str, status_msg_id: int):
        """Telegram-специфичная отправка аудио"""
        from aiogram.types import FSInputFile
        
        # Отправляем аудио с метаданными
        await self.messenger.send_media(
            chat_id=chat_id,
            media_type="audio",
            file_path=result.file_path,
            caption=f"✅ {result.metadata.title}\n👤 {result.metadata.author}"
        )
        
        # Удаляем статусное сообщение
        await self.messenger.delete_message(chat_id, status_msg_id)
        
        if result.from_cache:
            await self.messenger.send_message(
                chat_id=chat_id,
                text=self._t("served_from_cache", locale)
            )
    
    async def send_download_result(self, chat_id: int, result, quality: Quality, locale: str):
        """Telegram-специфичная отправка результата загрузки"""
        caption = (
            f"✅ <b>{result.metadata.title}</b>\n"
            f"👤 {result.metadata.author}\n"
            f"📦 {result.metadata.size_mb:.1f} MB\n"
            f"🎬 {quality.value}"
        )
        
        if result.from_cache:
            caption += f"\n\n💾 {self._t('served_from_cache', locale)}"
        
        # Определяем тип медиа и отправляем
        if result.metadata.media_type == MediaType.AUDIO:
            await self.messenger.send_media(
                chat_id=chat_id,
                media_type="audio",
                file_path=result.file_path,
                caption=caption
            )
        else:
            await self.messenger.send_media(
                chat_id=chat_id,
                media_type="video",
                file_path=result.file_path,
                caption=caption
            )
    
    def _get_locale(self, message_or_query) -> str:
        """Извлекает локаль из Telegram сообщения"""
        from_user = message_or_query.from_user if hasattr(message_or_query, 'from_user') else None
        if from_user and hasattr(from_user, 'language_code'):
            return from_user.language_code or settings.default_locale
        return settings.default_locale