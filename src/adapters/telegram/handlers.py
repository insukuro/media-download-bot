# src/adapters/telegram/handlers.py (замена целиком)
from aiogram import Dispatcher, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from loguru import logger
import hashlib
import json
import os
from datetime import datetime, timedelta

from ...core.downloader.interfaces import Quality, MediaType, DownloadStatus
from ...core.downloader.service import DownloadService
from ...core.cache.manager import FileCacheManager
from ...i18n.loader import i18n
from ...config import settings


# Кэш для временного хранения URL (используем тот же подход что и FileCacheManager)
class UrlStorage:
    """Временное хранилище URL с автоочисткой"""
    
    def __init__(self):
        self.storage_file = os.path.join(settings.base_dir, "url_storage.json")
        self._data = {}
        self._load()
    
    def _load(self):
        try:
            if os.path.exists(self.storage_file):
                with open(self.storage_file, 'r') as f:
                    self._data = json.load(f)
        except:
            self._data = {}
    
    def _save(self):
        try:
            with open(self.storage_file, 'w') as f:
                json.dump(self._data, f)
        except:
            pass
    
    def store(self, url: str) -> str:
        """Сохранить URL и вернуть короткий ключ"""
        clean_url = url.split('?')[0] if '?' in url else url
        key = hashlib.md5(clean_url.encode()).hexdigest()[:8]
        self._data[key] = {
            'url': clean_url,
            'created_at': datetime.now().isoformat()
        }
        self._save()
        return key
    
    def get(self, key: str) -> str:
        """Получить URL по ключу"""
        data = self._data.get(key)
        if data:
            return data['url']
        return key
    
    def cleanup(self, max_age_hours: int = 24):
        """Очистить старые записи"""
        now = datetime.now()
        to_delete = []
        for key, data in self._data.items():
            created = datetime.fromisoformat(data['created_at'])
            if now - created > timedelta(hours=max_age_hours):
                to_delete.append(key)
        for key in to_delete:
            del self._data[key]
        if to_delete:
            self._save()


# Глобальный инстанс хранилища URL
url_storage = UrlStorage()


def get_locale(from_user) -> str:
    """Получить локаль пользователя"""
    if from_user and hasattr(from_user, 'language_code'):
        return from_user.language_code or settings.default_locale
    return settings.default_locale


def translate(key: str, locale: str, **kwargs) -> str:
    """Краткий метод для получения перевода"""
    text = i18n.get_text(locale, key)
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, ValueError) as e:
            logger.warning(f"Format error for key '{key}': {e}")
            return text
    return text


def register_handlers(dp: Dispatcher, download_service: DownloadService):
    """Регистрация обработчиков команд"""
    
    @dp.message(Command("start"))
    async def cmd_start(message: types.Message):
        locale = get_locale(message.from_user)
        await message.answer(
            translate("welcome_message", locale) + "\n\n" + translate("help_message", locale)
        )
    
    @dp.message(Command("help"))
    async def cmd_help(message: types.Message):
        locale = get_locale(message.from_user)
        await message.answer(translate("help_message", locale))
    

    @dp.message(Command("yt"))
    async def cmd_youtube(message: types.Message):
        locale = get_locale(message.from_user)
        
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            await message.answer(_("yt_usage", locale))
            return
        
        url = args[1].strip()
        url_key = url_storage.store(url)
        status_msg = await message.answer(_("analyzing_url", locale))
        
        try:
            metadata = await download_service.get_metadata(url)
            
            # 🔥 ПОЛУЧАЕМ РЕАЛЬНО ДОСТУПНЫЕ КАЧЕСТВА
            available_qualities = await download_service.get_available_qualities(url)
            
            builder = InlineKeyboardBuilder()
            
            # Видео качества (только те что реально есть)
            video_qualities = [q for q in available_qualities if q in [Quality.LOW, Quality.MEDIUM, Quality.HIGH]]
            if video_qualities:
                for quality in video_qualities:
                    builder.button(
                        text=f"📹 {quality.value}",
                        callback_data=f"dl:{url_key}:{quality.value}:video"
                    )
                builder.adjust(len(video_qualities))
            
            # Аудио качества
            audio_qualities = [q for q in available_qualities if q in [Quality.AUDIO_LOW, Quality.AUDIO_MEDIUM, Quality.AUDIO_HIGH]]
            if audio_qualities:
                for quality in audio_qualities:
                    builder.button(
                        text=f"🎵 {quality.value}",
                        callback_data=f"dl:{url_key}:{quality.value}:audio"
                    )
                builder.adjust(len(audio_qualities))
            
            info_text = (
                f"<b>📹 {metadata.title}</b>\n\n"
                f"👤 <b>{_('author', locale)}:</b> {metadata.author}\n"
                f"⏱ <b>{_('duration', locale)}:</b> {metadata.duration_formatted}\n"
                f"📦 <b>{_('size', locale)}:</b> {metadata.size_mb:.1f} MB\n"
                f"🎬 <b>{_('type', locale)}:</b> {metadata.media_type.value}\n\n"
                f"<i>{_('select_quality', locale)}</i>"
            )
            
            if metadata.thumbnail_url:
                await message.answer_photo(
                    photo=metadata.thumbnail_url,
                    caption=info_text,
                    reply_markup=builder.as_markup()
                )
                await status_msg.delete()
            else:
                await status_msg.edit_text(info_text, reply_markup=builder.as_markup())
                
        except Exception as e:
            logger.error(f"Error processing YouTube URL: {e}")
            await status_msg.edit_text(
                _("error_processing_url", locale, error=str(e))
            )
    
    @dp.message(Command("tt"))
    async def cmd_tiktok(message: types.Message):
        locale = get_locale(message.from_user)
        
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            await message.answer(translate("tt_usage", locale))
            return
        
        url = args[1].strip()
        url_key = url_storage.store(url)
        status_msg = await message.answer(translate("analyzing_url", locale))
        
        try:
            metadata = await download_service.get_metadata(url)
            
            builder = InlineKeyboardBuilder()
            builder.button(
                text=translate("download_without_watermark", locale),
                callback_data=f"dl:{url_key}:{Quality.HIGH.value}:video"
            )
            
            info_text = (
                f"<b>🎵 {metadata.title}</b>\n\n"
                f"👤 <b>{translate('author', locale)}:</b> {metadata.author}\n"
                f"⏱ <b>{translate('duration', locale)}:</b> {metadata.duration_formatted}\n"
            )
            
            # Добавляем статистику если есть
            if metadata.extra.get('play_count'):
                info_text += f"👁 <b>{translate('views', locale)}:</b> {metadata.extra['play_count']}\n"
            if metadata.extra.get('digg_count'):
                info_text += f"❤️ <b>{translate('likes', locale)}:</b> {metadata.extra['digg_count']}\n"
            
            info_text += f"\n<i>{translate('without_watermark', locale)}</i>"
            
            if metadata.thumbnail_url:
                await message.answer_photo(
                    photo=metadata.thumbnail_url,
                    caption=info_text,
                    reply_markup=builder.as_markup()
                )
                await status_msg.delete()
            else:
                await status_msg.edit_text(info_text, reply_markup=builder.as_markup())
                
        except Exception as e:
            logger.error(f"Error processing TikTok URL: {e}")
            await status_msg.edit_text(
                translate("error_processing_url", locale, error=str(e))
            )
    
    @dp.message(Command("music"))
    async def cmd_music(message: types.Message):
        locale = get_locale(message.from_user)
        
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            await message.answer(translate("music_usage", locale))
            return
        
        url = args[1].strip()
        status_msg = await message.answer(translate("downloading_audio", locale))
        
        try:
            # Получаем метаданные
            metadata = await download_service.get_metadata(url)
            
            # Скачиваем аудио
            result = await download_service.download(
                url=url,
                quality=Quality.AUDIO_HIGH,
                user_id=str(message.from_user.id),
                media_type=MediaType.AUDIO
            )
            
            if result.status == DownloadStatus.COMPLETED:
                # Отправляем аудио с метаданными
                await message.answer_audio(
                    audio=types.FSInputFile(result.file_path),
                    title=result.metadata.title,
                    performer=result.metadata.author,
                    duration=result.metadata.duration,
                    caption=f"✅ {result.metadata.title}\n👤 {result.metadata.author}"
                )
                await status_msg.delete()
                
                if result.from_cache:
                    await message.answer(translate("served_from_cache", locale))
            else:
                await status_msg.edit_text(
                    translate("download_failed", locale, error=result.error)
                )
                
        except Exception as e:
            logger.error(f"Error downloading audio: {e}")
            await status_msg.edit_text(
                translate("error_processing_url", locale, error=str(e))
            )
    
    @dp.callback_query(lambda c: c.data.startswith("dl:"))
    async def process_download(callback_query: types.CallbackQuery):
        locale = get_locale(callback_query.from_user)
        
        try:
            parts = callback_query.data.split(":", 3)
            if len(parts) != 4:
                await callback_query.answer("Invalid callback data")
                return
            
            _, url_key, quality_str, media_type_str = parts
            url = url_storage.get(url_key)  # Восстанавливаем URL
            quality = Quality(quality_str)
            media_type = MediaType(media_type_str)
            
            await callback_query.answer()
            
            # Обновляем сообщение
            await callback_query.message.edit_caption(
                caption=f"⏳ <b>{translate('downloading', locale)}</b>\n\n"
                        f"<i>{translate('quality', locale)}: {quality.value}</i>"
            )
            
            # Скачиваем
            result = await download_service.download(
                url=url,
                quality=quality,
                user_id=str(callback_query.from_user.id),
                media_type=media_type
            )
            
            if result.status == DownloadStatus.COMPLETED:
                caption = (
                    f"✅ <b>{result.metadata.title}</b>\n"
                    f"👤 {result.metadata.author}\n"
                    f"📦 {result.metadata.size_mb:.1f} MB\n"
                    f"🎬 {quality.value}"
                )
                
                if result.from_cache:
                    caption += f"\n\n💾 {translate('served_from_cache', locale)}"
                
                if media_type == MediaType.AUDIO:
                    await callback_query.message.answer_audio(
                        audio=types.FSInputFile(result.file_path),
                        title=result.metadata.title,
                        performer=result.metadata.author,
                        duration=result.metadata.duration,
                        caption=caption
                    )
                else:
                    await callback_query.message.answer_video(
                        video=types.FSInputFile(result.file_path),
                        caption=caption,
                        duration=result.metadata.duration
                    )
                
                await callback_query.message.delete()
            else:
                await callback_query.message.edit_caption(
                    caption=f"❌ {translate('download_failed', locale, error=result.error)}"
                )
                
        except Exception as e:
            logger.error(f"Error in download callback: {e}")
            await callback_query.message.edit_caption(
                caption=f"❌ {translate('error_occurred', locale)}\n<i>{str(e)}</i>"
            )
    
    # Очистка старых URL при запуске
    url_storage.cleanup(max_age_hours=24)