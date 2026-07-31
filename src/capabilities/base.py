# src/capabilities/base.py
import os
from abc import ABC, abstractmethod
from typing import Any
from loguru import logger

from ..core.downloader.service import DownloadService
from ..core.downloader.interfaces import Quality, MediaType, DownloadStatus
from ..adapters.base import MessengerAdapter
from ..i18n.loader import i18n
from ..config import settings


class BaseCapability(ABC):
    """
    Базовый класс для всех capabilities.
    Содержит общую бизнес-логику загрузки медиа.
    """
    
    def __init__(
        self, 
        download_service: DownloadService,
        messenger: MessengerAdapter,
        url_storage: Any  # Интерфейс для хранения URL
    ):
        self.download_service = download_service
        self.messenger = messenger
        self.url_storage = url_storage
    
    # src/capabilities/base.py (process_url_command — добавить cached_qualities)
    async def process_url_command(self, url: str, chat_id: Any, user_id: str, locale: str, source_type: str):
        try:
            url_key = self.url_storage.store(url)
            status_msg_id = await self.send_status_message(chat_id, "analyzing_url", locale)
            
            try:
                metadata = await self.download_service.get_metadata(url)
                if not metadata or not metadata.title:
                    raise ValueError("Empty metadata received")
                
                available_qualities = await self.download_service.get_available_qualities(url)
                
                # Получаем кэшированные в Redis качества
                cached_qualities = []
                if hasattr(self.messenger, 'file_id_cache') and self.messenger.file_id_cache:
                    cached_qualities = await self.messenger.file_id_cache.get_cached_qualities(url)
                
                # Передаём cached_qualities в клавиатуру
                keyboard = self.build_quality_keyboard(url_key, available_qualities, cached_qualities)
                
                info_text = self._format_metadata_message(metadata, locale, source_type)
                
                await self.send_metadata_response(
                    chat_id=chat_id, text=info_text, keyboard=keyboard,
                    thumbnail_url=metadata.thumbnail_url, status_msg_id=status_msg_id
                )
            except Exception as e:
                logger.error(f"Error processing URL from {source_type}: {e}")
                try:
                    await self.messenger.send_message(
                        chat_id=chat_id,
                        text=self._t("error_processing_url", locale, error=str(e))
                    )
                except:
                    pass
        except Exception as e:
            logger.error(f"Critical error in process_url_command: {e}")
            await self.messenger.send_message(
                chat_id=chat_id,
                text=f"❌ Произошла ошибка: {str(e)}"
            )

    # src/capabilities/base.py (замена process_music_command)
    async def process_music_command(self, url: str, chat_id: Any, user_id: str, locale: str):
        status_msg_id = await self.send_status_message(chat_id, "downloading_audio", locale)

        try:
            quality = Quality.AUDIO_HIGH

            # 1. Проверяем FileIdCache
            if hasattr(self.messenger, 'file_id_cache') and self.messenger.file_id_cache:
                cached = await self.messenger.file_id_cache.get(url, quality)
                if cached:
                    logger.info(f"FileId cache hit for {url}")
                    await self.messenger.send_media_by_file_id(
                        chat_id=chat_id,
                        file_id=cached['file_id'],
                        media_type='audio',
                        caption="✅"
                    )
                    if status_msg_id:
                        await self.messenger.delete_message(chat_id, status_msg_id)
                    return

            # 2. Fallback: файловый кэш или загрузка
            task_id = await self.download_service.create_download_task(
                url=url, quality=quality, user_id=user_id, media_type=MediaType.AUDIO
            )
            result = await self.download_service.wait_for_task(task_id)

            if result.status == DownloadStatus.COMPLETED:
                await self.send_audio_result(chat_id=chat_id, result=result, locale=locale, status_msg_id=status_msg_id)
            else:
                await self.messenger.send_message(
                    chat_id=chat_id,
                    text=self._t("download_failed", locale, error=result.error)
                )

        except Exception as e:
            logger.error(f"Error downloading audio: {e}")
            await self.messenger.send_message(
                chat_id=chat_id,
                text=self._t("error_processing_url", locale, error=str(e))
            )
    
    # src/capabilities/base.py (process_download_callback — фикс caption)
    async def process_download_callback(self, callback_data: str, chat_id: Any, user_id: str, locale: str):
        try:
            parts = callback_data.split(":", 3)
            if len(parts) != 4:
                return

            _, url_key, quality_str, media_type_str = parts
            url = self.url_storage.get(url_key)
            quality = Quality(quality_str)
            # media_type из callback: vid -> video, aud -> audio
            media_type = MediaType.VIDEO if media_type_str == "vid" else MediaType.AUDIO

            await self.send_download_started(chat_id, quality, locale)

            # 1. FileIdCache
            if hasattr(self.messenger, 'file_id_cache') and self.messenger.file_id_cache:
                cached = await self.messenger.file_id_cache.get(url, quality)
                if cached:
                    logger.info(f"FileId cache hit for {url}")
                    try:
                        await self.messenger.send_media_by_file_id(
                            chat_id=chat_id,
                            file_id=cached['file_id'],
                            media_type=cached['media_type'],
                            caption=cached.get('caption', '✅')
                        )
                        return
                    except Exception as e:
                        logger.warning(f"FileId expired: {e}")
                        await self.messenger.file_id_cache.delete(url, quality)

            # 2. Загрузка
            task_id = await self.download_service.create_download_task(
                url=url, quality=quality, user_id=user_id, media_type=media_type
            )
            result = await self.download_service.wait_for_task(task_id)

            if result.status == DownloadStatus.COMPLETED:
                await self.send_download_result(chat_id=chat_id, result=result, quality=quality, locale=locale)
            else:
                await self.messenger.send_message(
                    chat_id=chat_id,
                    text=self._t("download_failed", locale, error=result.error)
                )

        except Exception as e:
            logger.error(f"Error in download callback: {e}")
            await self.messenger.send_message(
                chat_id=chat_id, text=self._t("error_occurred", locale, error=str(e))
            )
    
    def build_quality_keyboard(self, url_key: str, available_qualities: list) -> Any:
        """
        Строит клавиатуру с качествами.
        Должен быть переопределен в адаптер-специфичных capability.
        """
        raise NotImplementedError
    
    async def send_status_message(self, chat_id: Any, key: str, locale: str) -> Any:
        """Отправляет статусное сообщение. Возвращает ID сообщения."""
        return await self.messenger.send_message(
            chat_id=chat_id,
            text=self._t(key, locale)
        )
    
    async def send_metadata_response(self, chat_id: Any, text: str, keyboard: Any, 
                                   thumbnail_url: str, status_msg_id: Any):
        """Отправляет ответ с метаданными. Должен быть переопределен."""
        raise NotImplementedError
    
    async def send_audio_result(self, chat_id: Any, result, locale: str, status_msg_id: Any):
        """Отправляет результат загрузки аудио. Должен быть переопределен."""
        raise NotImplementedError
    
    async def send_download_started(self, chat_id: Any, quality: Quality, locale: str):
        """Сообщает о начале загрузки."""
        await self.messenger.send_message(
            chat_id=chat_id,
            text=f"⏳ {self._t('downloading', locale)} - {quality.value}"
        )
    
    async def send_download_result(self, chat_id: Any, result, quality: Quality, locale: str):
        """Отправляет результат загрузки. Должен быть переопределен."""
        raise NotImplementedError
    
    def _format_metadata_message(self, metadata, locale: str, source_type: str) -> str:
        """Форматирует сообщение с метаданными"""
        info_text = (
            f"<b>📹 {metadata.title}</b>\n\n"
            f"👤 <b>{self._t('author', locale)}:</b> {metadata.author}\n"
            f"⏱ <b>{self._t('duration', locale)}:</b> {metadata.duration_formatted}\n"
            f"📦 <b>{self._t('size', locale)}:</b> {metadata.size_mb:.1f} MB\n"
            f"🎬 <b>{self._t('type', locale)}:</b> {metadata.media_type.value}\n"
        )
        
        # Специфичная информация для источников
        if source_type == "tiktok" and metadata.extra:
            if metadata.extra.get('play_count'):
                info_text += f"👁 <b>{self._t('views', locale)}:</b> {metadata.extra['play_count']}\n"
            if metadata.extra.get('digg_count'):
                info_text += f"❤️ <b>{self._t('likes', locale)}:</b> {metadata.extra['digg_count']}\n"
        
        info_text += f"\n<i>{self._t('select_quality', locale)}</i>"
        return info_text
    
    def _t(self, key: str, locale: str, **kwargs) -> str:
        """Перевод строки"""
        text = i18n.get_text(locale, key)
        if kwargs:
            try:
                return text.format(**kwargs)
            except (KeyError, ValueError) as e:
                logger.warning(f"Format error for key '{key}': {e}")
                return text
        return text