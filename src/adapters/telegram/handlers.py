# src/adapters/telegram/handlers.py
from aiogram import Dispatcher, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from loguru import logger

from ...core.downloader.interfaces import Quality, MediaType, DownloadStatus
from ...core.downloader.service import DownloadService
from ...i18n.loader import i18n
from ...config import settings


def get_locale(from_user) -> str:
    """Получить локаль пользователя"""
    if from_user and hasattr(from_user, 'language_code'):
        return from_user.language_code or settings.default_locale
    return settings.default_locale


def _(key: str, locale: str, **kwargs) -> str:
    """Краткий метод для получения перевода"""
    text = i18n.get_text(locale, key)
    if kwargs:
        return text.format(**kwargs)
    return text


def register_handlers(dp: Dispatcher, download_service: DownloadService):
    """Регистрация обработчиков команд"""
    
    @dp.message(Command("start"))
    async def cmd_start(message: types.Message):
        locale = get_locale(message.from_user)
        await message.answer(
            _( "welcome_message", locale) + "\n\n" + _( "help_message", locale)
        )
    
    @dp.message(Command("help"))
    async def cmd_help(message: types.Message):
        locale = get_locale(message.from_user)
        await message.answer(_("help_message", locale))
    
    @dp.message(Command("yt"))
    async def cmd_youtube(message: types.Message):
        locale = get_locale(message.from_user)
        
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            await message.answer(_("yt_usage", locale))
            return
        
        url = args[1].strip()
        status_msg = await message.answer(_("analyzing_url", locale))
        
        try:
            metadata = await download_service.get_metadata(url)
            
            builder = InlineKeyboardBuilder()
            
            # Видео качества
            for quality in [Quality.LOW, Quality.MEDIUM, Quality.HIGH]:
                builder.button(
                    text=f"📹 {quality.value}",
                    callback_data=f"dl:{url}:{quality.value}:video"
                )
            builder.adjust(3)
            
            # Аудио качества
            for quality in [Quality.AUDIO_LOW, Quality.AUDIO_MEDIUM, Quality.AUDIO_HIGH]:
                builder.button(
                    text=f"🎵 {quality.value}",
                    callback_data=f"dl:{url}:{quality.value}:audio"
                )
            builder.adjust(3)
            
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
            await message.answer(_("tt_usage", locale))
            return
        
        url = args[1].strip()
        status_msg = await message.answer(_("analyzing_url", locale))
        
        try:
            metadata = await download_service.get_metadata(url)
            
            builder = InlineKeyboardBuilder()
            builder.button(
                text=_("download_without_watermark", locale),
                callback_data=f"dl:{url}:{Quality.HIGH.value}:video"
            )
            
            info_text = (
                f"<b>🎵 {metadata.title}</b>\n\n"
                f"👤 <b>{_('author', locale)}:</b> {metadata.author}\n"
                f"⏱ <b>{_('duration', locale)}:</b> {metadata.duration_formatted}\n"
            )
            
            # Добавляем статистику если есть
            if metadata.extra.get('play_count'):
                info_text += f"👁 <b>{_('views', locale)}:</b> {metadata.extra['play_count']}\n"
            if metadata.extra.get('digg_count'):
                info_text += f"❤️ <b>{_('likes', locale)}:</b> {metadata.extra['digg_count']}\n"
            
            info_text += f"\n<i>{_('without_watermark', locale)}</i>"
            
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
                _("error_processing_url", locale, error=str(e))
            )
    
    @dp.message(Command("music"))
    async def cmd_music(message: types.Message):
        locale = get_locale(message.from_user)
        
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            await message.answer(_("music_usage", locale))
            return
        
        url = args[1].strip()
        status_msg = await message.answer(_("downloading_audio", locale))
        
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
                    await message.answer(_("served_from_cache", locale))
            else:
                await status_msg.edit_text(
                    _("download_failed", locale, error=result.error)
                )
                
        except Exception as e:
            logger.error(f"Error downloading audio: {e}")
            await status_msg.edit_text(
                _("error_processing_url", locale, error=str(e))
            )
    
    @dp.callback_query(lambda c: c.data.startswith("dl:"))
    async def process_download(callback_query: types.CallbackQuery):
        locale = get_locale(callback_query.from_user)
        
        try:
            _, url, quality_str, media_type_str = callback_query.data.split(":", 3)
            quality = Quality(quality_str)
            media_type = MediaType(media_type_str)
            
            await callback_query.answer()
            
            # Обновляем сообщение
            await callback_query.message.edit_caption(
                caption=f"⏳ <b>{_('downloading', locale)}</b>\n\n"
                        f"<i>{_('quality', locale)}: {quality.value}</i>"
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
                    caption += f"\n\n💾 {_('served_from_cache', locale)}"
                
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
                    caption=f"❌ {_('download_failed', locale, error=result.error)}"
                )
                
        except Exception as e:
            logger.error(f"Error in download callback: {e}")
            await callback_query.message.edit_caption(
                caption=f"❌ {_('error_occurred', locale)}\n<i>{str(e)}</i>"
            )