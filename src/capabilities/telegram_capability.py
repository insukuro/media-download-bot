# src/capabilities/telegram_capability.py
from aiogram import Dispatcher, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from loguru import logger

from .base import BaseCapability
from ..core.downloader.interfaces import Quality, MediaType, DownloadStatus
from ..config import settings


class TelegramCapability(BaseCapability):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._handlers_registered = False

    def register_handlers(self, dp: Dispatcher):
        if self._handlers_registered:
            return
        self._handlers_registered = True

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
                chat_id=message.chat.id, text=self._t("help_message", locale)
            )

        @dp.message(Command("yt"))
        async def cmd_youtube(message: types.Message):
            locale = self._get_locale(message)
            args = message.text.split(maxsplit=1)
            if len(args) < 2:
                await self.messenger.send_message(chat_id=message.chat.id, text=self._t("yt_usage", locale))
                return
            await self.process_url_command(
                url=args[1].strip(), chat_id=message.chat.id,
                user_id=str(message.from_user.id), locale=locale, source_type="youtube"
            )

        @dp.message(Command("tt"))
        async def cmd_tiktok(message: types.Message):
            locale = self._get_locale(message)
            args = message.text.split(maxsplit=1)
            if len(args) < 2:
                await self.messenger.send_message(chat_id=message.chat.id, text=self._t("tt_usage", locale))
                return
            await self.process_url_command(
                url=args[1].strip(), chat_id=message.chat.id,
                user_id=str(message.from_user.id), locale=locale, source_type="tiktok"
            )

        @dp.message(Command("music"))
        async def cmd_music(message: types.Message):
            locale = self._get_locale(message)
            args = message.text.split(maxsplit=1)
            if len(args) < 2:
                await self.messenger.send_message(chat_id=message.chat.id, text=self._t("music_usage", locale))
                return
            await self.process_music_command(
                url=args[1].strip(), chat_id=message.chat.id,
                user_id=str(message.from_user.id), locale=locale
            )

        @dp.callback_query(lambda c: c.data.startswith("dl:"))
        async def process_download(callback_query: types.CallbackQuery):
            locale = self._get_locale(callback_query)
            await self.messenger.answer_callback(callback_query.id)
            await self.process_download_callback(
                callback_data=callback_query.data,
                chat_id=callback_query.message.chat.id,
                user_id=str(callback_query.from_user.id),
                locale=locale
            )
            await self.messenger.delete_message(
                chat_id=callback_query.message.chat.id,
                message_id=callback_query.message.message_id
            )

    def build_quality_keyboard(self, url_key: str, available_qualities: list, cached_qualities: list = None):
        """Клавиатура с компактными callback_data"""
        if cached_qualities is None:
            cached_qualities = []

        builder = InlineKeyboardBuilder()

        video_qualities = [q for q in available_qualities
                          if q in [Quality.LOW, Quality.MEDIUM, Quality.HIGH]]
        for quality in video_qualities:
            prefix = "✅ " if quality in cached_qualities else ""
            builder.button(
                text=f"{prefix}📹 {quality.value}",
                callback_data=f"dl:{url_key}:{quality.value}:vid"
            )
        if video_qualities:
            builder.adjust(len(video_qualities))

        audio_qualities = [q for q in available_qualities
                          if q in [Quality.AUDIO_LOW, Quality.AUDIO_MEDIUM, Quality.AUDIO_HIGH]]
        for quality in audio_qualities:
            prefix = "✅ " if quality in cached_qualities else ""
            builder.button(
                text=f"{prefix}🎵 {quality.value}",
                callback_data=f"dl:{url_key}:{quality.value}:aud"
            )
        if audio_qualities:
            builder.adjust(len(audio_qualities))

        return builder.as_markup()

    async def send_metadata_response(self, chat_id: int, text: str, keyboard,
                                     thumbnail_url: str, status_msg_id: int):
        """Отправляет фото с клавиатурой, без дубля"""
        try:
            if thumbnail_url and thumbnail_url.startswith(('http://', 'https://')):
                try:
                    await self.messenger.send_photo(
                        chat_id=chat_id, photo_path=thumbnail_url, caption=text
                    )
                except Exception as e:
                    logger.warning(f"Failed to send thumbnail: {e}")
                    await self.messenger.send_message(chat_id=chat_id, text=text)
            else:
                await self.messenger.send_message(chat_id=chat_id, text=text)

            # Клавиатура ОДНИМ сообщением, без лишнего текста
            await self.messenger.send_message(
                chat_id=chat_id,
                text=self._t("select_quality", "ru"),
                reply_markup=keyboard
            )

            if status_msg_id:
                await self.messenger.delete_message(chat_id, status_msg_id)
        except Exception as e:
            logger.error(f"Failed to send metadata response: {e}")
            await self.messenger.send_message(chat_id=chat_id, text=text, reply_markup=keyboard)

    async def send_audio_result(self, chat_id: int, result, locale: str, status_msg_id: int):
        caption = f"✅ {result.metadata.title}\n👤 {result.metadata.author}"
        await self.messenger.send_media(
            chat_id=chat_id, media_type="audio", file_path=result.file_path,
            caption=caption,
            url=result.metadata.url,
            quality=result.metadata.quality.value if result.metadata.quality else None
        )
        if status_msg_id:
            await self.messenger.delete_message(chat_id, status_msg_id)

    async def send_download_result(self, chat_id: int, result, quality: Quality, locale: str):
        caption = (
            f"✅ <b>{result.metadata.title}</b>\n"
            f"👤 {result.metadata.author}\n"
            f"📦 {result.metadata.size_mb:.1f} MB\n"
            f"🎬 {quality.value}"
        )

        # Пробуем file_id
        if hasattr(self.messenger, 'file_id_cache') and self.messenger.file_id_cache:
            cached = await self.messenger.file_id_cache.get(result.metadata.url, quality)
            if cached and cached.get('caption'):  # есть сохранённый caption
                try:
                    await self.messenger.send_media_by_file_id(
                        chat_id=chat_id, file_id=cached['file_id'],
                        media_type=cached['media_type'], caption=cached['caption']
                    )
                    return
                except Exception as e:
                    logger.warning(f"FileId expired: {e}")
                    await self.messenger.file_id_cache.delete(result.metadata.url, quality)

        # Fallback
        media_type = "audio" if result.metadata.media_type == MediaType.AUDIO else "video"
        await self.messenger.send_media(
            chat_id=chat_id, media_type=media_type, file_path=result.file_path,
            caption=caption, url=result.metadata.url, quality=quality.value
        )

    def _get_locale(self, message_or_query) -> str:
        from_user = message_or_query.from_user if hasattr(message_or_query, 'from_user') else None
        if from_user and hasattr(from_user, 'language_code'):
            return from_user.language_code or settings.default_locale
        return settings.default_locale