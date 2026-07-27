import asyncio
import hashlib
import uuid
from typing import Dict, List, Optional
from loguru import logger

from .interfaces import (
    SourceDownloader, CacheManager, DownloadQueue,
    MediaMetadata, DownloadResult, DownloadTask,
    DownloadStatus, Quality, MediaType
)
from .exceptions import *
from ...config import settings


class DownloadService:
    """Основной сервис загрузки"""
    
    def __init__(
        self,
        sources: Dict[str, SourceDownloader],
        cache: CacheManager,
        queue: DownloadQueue
    ):
        self.sources = sources
        self.cache = cache
        self.queue = queue
        self._download_lock = asyncio.Semaphore(settings.max_concurrent_downloads)
    
    async def get_metadata(self, url: str) -> MediaMetadata:
        """Получить метаданные медиафайла"""
        source = self._resolve_source(url)
        return await source.extract_metadata(url)
    
    async def get_available_qualities(self, url: str) -> List[Quality]:
        """Получить доступные качества"""
        source = self._resolve_source(url)
        return await source.get_available_qualities(url)
    
    async def download(
        self,
        url: str,
        quality: Quality,
        user_id: str,
        media_type: Optional[MediaType] = None
    ) -> DownloadResult:
        """Скачать медиафайл с кэшированием"""
        
        # Определяем тип медиа
        if not media_type:
            media_type = self._detect_media_type(quality)
        
        # Проверяем кэш
        cache_key = self._get_cache_key(url, quality)
        if await self.cache.exists(url, quality):
            logger.info(f"Cache hit: {url}")
            cached = await self.cache.get(url, quality)
            cached.from_cache = True
            return cached
        
        # Создаем задачу
        task = DownloadTask(
            id=str(uuid.uuid4()),
            url=url,
            media_type=media_type,
            quality=quality,
            user_id=user_id
        )
        
        # Добавляем в очередь
        await self.queue.enqueue(task)
        
        # Ждем выполнения
        result = await self._process_download(task)
        
        # Сохраняем в кэш
        if result.status == DownloadStatus.COMPLETED:
            await self.cache.set(url, quality, result)
        
        return result
    
    async def download_playlist(
        self,
        url: str,
        quality: Quality,
        user_id: str,
        limit: Optional[int] = None
    ) -> List[DownloadTask]:
        """Скачать плейлист"""
        source = self._resolve_source(url)
        
        # Получаем список видео
        try:
            video_urls = await source.get_playlist(url, limit)
        except NotImplementedError:
            raise UnsupportedSourceException("Playlist not supported for this source")
        
        # Создаем задачи
        tasks = []
        for video_url in video_urls:
            task = DownloadTask(
                id=str(uuid.uuid4()),
                url=video_url,
                media_type=MediaType.VIDEO,
                quality=quality,
                user_id=user_id
            )
            await self.queue.enqueue(task)
            tasks.append(task)
        
        return tasks
    

    async def _process_download(self, task: DownloadTask) -> DownloadResult:
        """Обработка загрузки с контролем параллелизма"""
        async with self._download_lock:
            try:
                source = self._resolve_source(task.url)
                task.status = DownloadStatus.DOWNLOADING
                await self.queue.update_task(task)
                
                # 🔥 Синхронный коллбэк (без asyncio.create_task)
                def progress_callback(percent: float):
                    task.progress = percent
                    # Не вызываем асинхронные методы здесь!
                
                # Загружаем
                result = await source.download(
                    task.url,
                    task.quality,
                    progress_callback
                )
                
                task.status = DownloadStatus.COMPLETED
                task.result = result
                await self.queue.update_task(task)
                
                return result
                
            except Exception as e:
                logger.error(f"Download failed: {task.url}, error: {str(e)}")
                task.status = DownloadStatus.FAILED
                task.result = DownloadResult(
                    file_path="",
                    metadata=MediaMetadata(
                        url=task.url,
                        title="",
                        author="",
                        duration=0
                    ),
                    status=DownloadStatus.FAILED,
                    error=str(e)
                )
                await self.queue.update_task(task)
                return task.result
    
    def _resolve_source(self, url: str) -> SourceDownloader:
        """Определить источник по URL"""
        if "youtube.com" in url or "youtu.be" in url:
            if not settings.youtube_enabled:
                raise UnsupportedSourceException("YouTube is disabled")
            return self.sources.get("youtube")
        elif "tiktok.com" in url:
            if not settings.tiktok_enabled:
                raise UnsupportedSourceException("TikTok is disabled")
            return self.sources.get("tiktok")
        else:
            raise UnsupportedSourceException(f"Unsupported URL: {url}")
    
    def _detect_media_type(self, quality: Quality) -> MediaType:
        """Определить тип медиа по качеству"""
        if quality in [Quality.AUDIO_LOW, Quality.AUDIO_MEDIUM, Quality.AUDIO_HIGH]:
            return MediaType.AUDIO
        return MediaType.VIDEO
    
    def _get_cache_key(self, url: str, quality: Quality) -> str:
        """Сгенерировать ключ кэша"""
        key = f"{url}:{quality.value}"
        return hashlib.md5(key.encode()).hexdigest()
    
    async def get_stats(self) -> Dict:
        """Получить статистику сервиса"""
        cache_stats = await self.cache.get_stats()
        queue_size = await self.queue.get_queue_size()
        
        return {
            "cache": cache_stats,
            "queue_size": queue_size,
            "max_concurrent_downloads": settings.max_concurrent_downloads
        }