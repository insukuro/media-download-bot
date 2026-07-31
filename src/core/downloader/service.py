# src/core/downloader/service.py (исправленная _process_download)
import asyncio
import hashlib
import uuid
import os
from typing import Dict, List, Optional
from loguru import logger
from datetime import datetime

from .interfaces import (
    SourceDownloader, CacheManager, DownloadQueue,
    MediaMetadata, DownloadResult, DownloadTask,
    DownloadStatus, Quality, MediaType
)
from .exceptions import *
from ...config import settings


class DownloadService:
    """Основной сервис загрузки с worker pool"""
    
    def __init__(
        self,
        sources: Dict[str, SourceDownloader],
        cache: CacheManager,
        queue: DownloadQueue
    ):
        self.sources = sources
        self.cache = cache
        self.queue = queue
        self._workers: List[asyncio.Task] = []
        self._running = False
        
        # Семафор для контроля параллельных загрузок
        self._download_semaphore = asyncio.Semaphore(settings.max_concurrent_downloads)
        
        # Очистка старых задач при старте
        self._cleanup_task = None
    
    async def start(self):
        """Запускает worker pool для параллельной загрузки"""
        self._running = True
        
        # Запускаем воркеров
        for i in range(settings.max_concurrent_downloads):
            worker = asyncio.create_task(self._worker(i))
            self._workers.append(worker)
        
        # Запускаем периодическую очистку
        self._cleanup_task = asyncio.create_task(self._periodic_cleanup())
        
        logger.info(f"Started {settings.max_concurrent_downloads} download workers")
    
    async def stop(self):
        """Останавливает worker pool"""
        self._running = False
        
        # Останавливаем очистку
        if self._cleanup_task:
            self._cleanup_task.cancel()
        
        # Ждем завершения всех воркеров
        for worker in self._workers:
            worker.cancel()
        
        await asyncio.gather(*self._workers, return_exceptions=True)
        logger.info("Download workers stopped")
    
    async def _worker(self, worker_id: int):
        """Worker процесс для параллельной загрузки"""
        logger.info(f"Download worker {worker_id} started")
        
        while self._running:
            try:
                # Ждем задачу из очереди
                task = await self.queue.dequeue()
                
                if task:
                    logger.info(f"Worker {worker_id} processing task {task.id}")
                    
                    # Используем семафор для контроля параллелизма
                    async with self._download_semaphore:
                        result = await self._process_download(task)
                    
                    # Сохраняем в кэш если успешно
                    if result.status == DownloadStatus.COMPLETED:
                        try:
                            await self.cache.set(task.url, task.quality, result)
                        except Exception as e:
                            logger.error(f"Failed to cache result: {e}")
                    
                    # Обновляем задачу
                    task.result = result
                    await self.queue.update_task(task)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker {worker_id} error: {e}", exc_info=True)
                await asyncio.sleep(1)
        
        logger.info(f"Download worker {worker_id} stopped")
    
    async def _periodic_cleanup(self):
        """Периодическая очистка старых задач"""
        while self._running:
            try:
                await asyncio.sleep(3600)  # Каждый час
                await self.queue.clear_completed(max_age_hours=24)
                await self.cache.cleanup_old_entries()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup error: {e}")
    
    async def create_download_task(
        self,
        url: str,
        quality: Quality,
        user_id: str,
        media_type: Optional[MediaType] = None
    ) -> str:
        """Создает задачу на загрузку и добавляет в очередь"""
        
        if not media_type:
            media_type = self._detect_media_type(quality)
        
        # Проверяем кэш
        if await self.cache.exists(url, quality):
            logger.info(f"Cache hit for {url}")
            cached_result = await self.cache.get(url, quality)
            
            if cached_result:
                cached_result.from_cache = True
                
                # Создаем "мгновенную" задачу
                task = DownloadTask(
                    id=str(uuid.uuid4()),
                    url=url,
                    media_type=media_type,
                    quality=quality,
                    user_id=user_id,
                    status=DownloadStatus.COMPLETED,
                    result=cached_result
                )
                
                # Добавляем в завершенные
                task.completed_at = datetime.now()
                await self.queue.update_task(task)
                
                # Сразу сигнализируем о завершении
                if hasattr(self.queue, '_completion_events'):
                    event = asyncio.Event()
                    self.queue._completion_events[task.id] = event
                    event.set()
                
                return task.id
        
        # Создаем новую задачу
        task = DownloadTask(
            id=str(uuid.uuid4()),
            url=url,
            media_type=media_type,
            quality=quality,
            user_id=user_id
        )
        
        # Добавляем в очередь
        await self.queue.enqueue(task)
        
        return task.id
    
    async def wait_for_task(self, task_id: str, timeout: int = None) -> DownloadResult:
        """Ожидает завершения задачи"""
        timeout = timeout or settings.download_timeout_seconds
        
        try:
            task = await self.queue.wait_for_completion(task_id, timeout)
            if task and task.result:
                return task.result
            elif task:
                return DownloadResult(
                    file_path="",
                    metadata=MediaMetadata(url="", title="", author="", duration=0),
                    status=DownloadStatus.FAILED,
                    error=task.error or "Unknown error"
                )
            else:
                raise ValueError(f"Task {task_id} not found")
        except TimeoutError:
            return DownloadResult(
                file_path="",
                metadata=MediaMetadata(url="", title="", author="", duration=0),
                status=DownloadStatus.FAILED,
                error="Download timeout"
            )
    
    async def get_metadata(self, url: str) -> MediaMetadata:
        """Получить метаданные медиафайла"""
        source = self._resolve_source(url)
        return await source.extract_metadata(url)
    
    async def get_available_qualities(self, url: str) -> List[Quality]:
        """Получить доступные качества"""
        source = self._resolve_source(url)
        return await source.get_available_qualities(url)
    
    async def _process_download(self, task: DownloadTask) -> DownloadResult:
        """Обработка загрузки с проверками"""
        try:
            source = self._resolve_source(task.url)
            
            # Проверяем размер файла перед загрузкой если возможно
            try:
                metadata = await source.extract_metadata(task.url)
                if metadata.size > 0:
                    max_size = settings.max_file_size_mb * 1024 * 1024
                    if metadata.size > max_size:
                        raise DownloadFailedException(
                            f"File too large: {metadata.size_mb:.1f}MB (max: {settings.max_file_size_mb}MB)"
                        )
            except DownloadFailedException:
                raise
            except Exception as e:
                logger.warning(f"Could not check file size: {e}")
            
            # Прогресс коллбэк (не асинхронный!)
            def progress_callback(percent: float):
                task.progress = percent
                logger.debug(f"Task {task.id} progress: {percent:.1f}%")
            
            # Загружаем
            result = await source.download(
                task.url,
                task.quality,
                progress_callback
            )
            
            # Проверяем результат
            if not result or not result.file_path:
                raise DownloadFailedException("Download returned empty result")
            
            if not os.path.exists(result.file_path):
                raise DownloadFailedException(f"Downloaded file not found: {result.file_path}")
            
            # Проверяем финальный размер
            file_size = os.path.getsize(result.file_path)
            max_size = settings.max_file_size_mb * 1024 * 1024
            
            if file_size > max_size:
                os.remove(result.file_path)  # Удаляем слишком большой файл
                raise DownloadFailedException(
                    f"Downloaded file too large: {file_size / (1024*1024):.1f}MB "
                    f"(max: {settings.max_file_size_mb}MB)"
                )
            
            # Обновляем размер в метаданных
            result.metadata.size = file_size
            result.metadata.quality = task.quality
            
            task.status = DownloadStatus.COMPLETED
            return result
            
        except Exception as e:
            logger.error(f"Download failed: {task.url}, error: {str(e)}")
            task.status = DownloadStatus.FAILED
            task.error = str(e)
            
            return DownloadResult(
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
    
    def _resolve_source(self, url: str) -> SourceDownloader:
        """Определить источник по URL"""
        if not url:
            raise UnsupportedSourceException("Empty URL")
        
        if "youtube.com" in url or "youtu.be" in url:
            if not settings.youtube_enabled:
                raise UnsupportedSourceException("YouTube is disabled")
            source = self.sources.get("youtube")
        elif "tiktok.com" in url:
            if not settings.tiktok_enabled:
                raise UnsupportedSourceException("TikTok is disabled")
            source = self.sources.get("tiktok")
        else:
            raise UnsupportedSourceException(f"Unsupported URL: {url}")
        
        if not source:
            raise UnsupportedSourceException(f"Source not configured for: {url}")
        
        return source
    
    def _detect_media_type(self, quality: Quality) -> MediaType:
        """Определить тип медиа по качеству"""
        if quality in [Quality.AUDIO_LOW, Quality.AUDIO_MEDIUM, Quality.AUDIO_HIGH]:
            return MediaType.AUDIO
        return MediaType.VIDEO