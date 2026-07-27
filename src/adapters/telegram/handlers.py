from aiogram import Dispatcher, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from loguru import logger

from ...core.downloader.interfaces import Quality, MediaType, DownloadStatus
from ...core.downloader.service import DownloadService
from ...i18n.loader import i18n
from ...config import settings


def register_handlers(dp: Dispatcher, download_service: DownloadService):
    """Регистрация обработчиков команд"""
    
    @dp.message(Command("start"))
    async def cmd_start(message: types.Message):
        """Обработчик команды /start"""
        locale = message.from_user.language_code or settings.default_locale
        
        welcome_text = i18n.get_text(locale, "welcome_message")
        help_text = i18n.get_text(locale, "help_message")
        
        await message.answer(f"{welcome_text}\n\n{help_text}")
    
    @dp.message(Command("help"))
    async def cmd_help(message: types.Message):
        """Обработчик команды /help"""
        locale = message.from_user.language_code or settings.default_locale
        help_text = i18n.get_text(locale, "help_message")
        await message.answer(help_text)
    
    @dp.message(Command("yt"))
    async def cmd_youtube(message: types.Message):
        """Обработчик команды /yt - скачать YouTube видео"""
        locale = message.from_user.language_code or settings.default_locale
        
        # Получаем URL из команды
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            await message.answer(i18n.get_text(locale, "yt_usage"))
            return
        
        url = args[1].strip()
        
        # Отправляем сообщение о начале обработки
        status_msg = await message.answer(
            i18n.get_text(locale, "analyzing_url")
        )
        
        try:
            # Получаем метаданные
            metadata = await download_service.get_metadata(url)
            
            # Создаем клавиатуру выбора качества
            builder = InlineKeyboardBuilder()
            
            # Видео качества
            for quality in [Quality.LOW, Quality.MEDIUM, Quality.HIGH]:
                builder.button(
                    text=f"📹 {quality.value}",
                    callback_data=f"download:{url}:{quality.value}:video"
                )
            
            builder.adjust(3)
            
            # Аудио качества
            for quality in [Quality.AUDIO_LOW, Quality.AUDIO_MEDIUM, Quality.AUDIO_HIGH]:
                builder.button(
                    text=f"🎵 {quality.value}",
                    callback_data=f"download:{url}:{quality.value}:audio"
                )
            
            builder.adjust(3)
            
            # Информация о видео
            info_text = (
                f"<b>📹 {metadata.title}</b>\n\n"
                f"👤 <b>Автор:</b> {metadata.author}\n"
                f"⏱ <b>Длительность:</b> {metadata.duration_formatted}\n"
                f"📦 <b>Размер:</b> {metadata.size_mb:.1f} MB\n"
                f"🎬 <b>Тип:</b> {metadata.media_type.value}\n\n"
                f"<i>Выберите качество для скачивания:</i>"
            )
            
            # Отправляем с превью
            if metadata.thumbnail_url:
                await message.answer_photo(
                    photo=metadata.thumbnail_url,
                    caption=info_text,
                    reply_markup=builder.as_markup()
                )
            else:
                await status_msg.edit_text(
                    info_text,
                    reply_markup=builder.as_markup()
                )
                
        except Exception as e:
            logger.error(f"Error processing YouTube URL: {e}")
            await status_msg.edit_text(
                i18n.get_text(locale, "error_processing_url").format(error=str(e))
            )
    
    @dp.message(Command("tt"))
    async def cmd_tiktok(message: types.Message):
        """Обработчик команды /tt - скачать TikTok видео"""
        locale = message.from_user.language_code or settings.default_locale
        
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            await message.answer(i18n.get_text(locale, "tt_usage"))
            return
        
        url = args[1].strip()
        
        status_msg = await message.answer(
            i18n.get_text(locale, "analyzing_url")
        )
        
        try:
            metadata = await download_service.get_metadata(url)
            
            # TikTok только в одном качестве
            builder = InlineKeyboardBuilder()
            builder.button(
                text="🎬 Скачать без водяного знака",
                callback_data=f"download:{url}:{Quality.HIGH.value}:video"
            )
            
            info_text = (
                f"<b>🎵 {metadata.title}</b>\n\n"
                f"👤 <b>Автор:</b> {metadata.author}\n"
                f"⏱ <b>Длительность:</b> {metadata.duration_formatted}\n"
                f"📊 <b>Просмотров:</b> {metadata.extra.get('play_count', 0)}\n"
                f"❤️ <b>Лайков:</b> {metadata.extra.get('digg_count', 0)}\n\n"
                f"<i>Видео будет скачано без водяного знака</i>"
            )
            
            if metadata.thumbnail_url:
                await message.answer_photo(
                    photo=metadata.thumbnail_url,
                    caption=info_text,
                    reply_markup=builder.as_markup()
                )
            else:
                await status_msg.edit_text(
                    info_text,
                    reply_markup=builder.as_markup()
                )
                
        except Exception as e:
            logger.error(f"Error processing TikTok URL: {e}")
            await status_msg.edit_text(
                i18n.get_text(locale, "error_processing_url").format(error=str(e))
            )
    
    @dp.message(Command("music"))
    async def cmd_music(message: types.Message):
        """Обработчик команды /music - скачать аудио"""
        locale = message.from_user.language_code or settings.default_locale
        
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            await message.answer(i18n.get_text(locale, "music_usage"))
            return
        
        url = args[1].strip()
        
        # Автоматически скачиваем в аудио качестве
        status_msg = await message.answer(
            i18n.get_text(locale, "downloading_audio")
        )
        
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
                # Отправляем аудио
                await message.answer_audio(
                    audio=open(result.file_path, 'rb'),
                    title=result.metadata.title,
                    performer=result.metadata.author,
                    duration=result.metadata.duration,
                    thumb=open(result.metadata.thumbnail_url, 'rb') if result.metadata.thumbnail_url else None
                )
                await status_msg.delete()
                
                if result.from_cache:
                    await message.answer(i18n.get_text(locale, "served_from_cache"))
            else:
                await status_msg.edit_text(
                    i18n.get_text(locale, "download_failed").format(error=result.error)
                )
                
        except Exception as e:
            logger.error(f"Error downloading audio: {e}")
            await status_msg.edit_text(
                i18n.get_text(locale, "error_processing_url").format(error=str(e))
            )
    
    @dp.callback_query(lambda c: c.data.startswith("download:"))
    async def process_download(callback_query: types.CallbackQuery):
        """Обработка callback для скачивания"""
        locale = callback_query.from_user.language_code or settings.default_locale
        
        try:
            # Парсим данные
            _, url, quality_str, media_type_str = callback_query.data.split(":", 3)
            quality = Quality(quality_str)
            media_type = MediaType(media_type_str)
            
            # Отвечаем на callback
            await callback_query.answer()
            
            # Обновляем сообщение
            await callback_query.message.edit_caption(
                caption=f"⏳ <b>{i18n.get_text(locale, 'downloading')}</b>\n\n"
                        f"<i>{i18n.get_text(locale, 'quality')}: {quality.value}</i>"
            )
            
            # Скачиваем
            result = await download_service.download(
                url=url,
                quality=quality,
                user_id=str(callback_query.from_user.id),
                media_type=media_type
            )
            
            if result.status == DownloadStatus.COMPLETED:
                # Отправляем результат
                caption = (
                    f"✅ <b>{result.metadata.title}</b>\n"
                    f"👤 {result.metadata.author}\n"
                    f"📦 {result.metadata.size_mb:.1f} MB\n"
                    f"🎬 {quality.value}"
                )
                
                if result.from_cache:
                    caption += f"\n\n💾 {i18n.get_text(locale, 'served_from_cache')}"
                
                if media_type == MediaType.AUDIO:
                    await callback_query.message.answer_audio(
                        audio=open(result.file_path, 'rb'),
                        title=result.metadata.title,
                        performer=result.metadata.author,
                        duration=result.metadata.duration,
                        caption=caption
                    )
                else:
                    await callback_query.message.answer_video(
                        video=open(result.file_path, 'rb'),
                        caption=caption,
                        duration=result.metadata.duration
                    )
                
                # Удаляем сообщение с выбором качества
                await callback_query.message.delete()
            else:
                await callback_query.message.edit_caption(
                    caption=f"❌ {i18n.get_text(locale, 'download_failed')}\n"
                            f"<i>{result.error}</i>"
                )
                
        except Exception as e:
            logger.error(f"Error in download callback: {e}")
            await callback_query.message.edit_caption(
                caption=f"❌ {i18n.get_text(locale, 'error_occurred')}\n"
                        f"<i>{str(e)}</i>"
            )
    
    @dp.message(Command("admin"))
    async def cmd_admin(message: types.Message):
        """Админ-панель"""
        locale = message.from_user.language_code or settings.default_locale
        
        # Проверяем админа
        if message.from_user.id not in settings.telegram_admin_ids:
            await message.answer(i18n.get_text(locale, "access_denied"))
            return
        
        # Получаем статистику
        stats = await download_service.get_stats()
        
        admin_text = (
            "<b>📊 Админ-панель MediaDownloader</b>\n\n"
            f"<b>Кэш:</b>\n"
            f"• Записей: {stats['cache']['entries']}\n"
            f"• Размер: {stats['cache']['total_size_mb']:.1f} MB\n"
            f"• Лимит: {stats['cache']['max_size_gb']} GB\n\n"
            f"<b>Очередь:</b>\n"
            f"• В очереди: {stats['queue_size']}\n"
            f"• Макс. одновременных: {stats['max_concurrent_downloads']}\n\n"
            f"<i>Обновлено: {__import__('datetime').datetime.now().strftime('%H:%M:%S')}</i>"
        )
        
        await message.answer(admin_text)