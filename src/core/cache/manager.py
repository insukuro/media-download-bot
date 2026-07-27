# src/core/cache/manager.py
import os
import json
import shutil
import asyncio
import hashlib
from typing import Dict, Optional
from datetime import datetime, timedelta
from loguru import logger

from ..downloader.interfaces import CacheManager, DownloadResult, Quality
from ..downloader.exceptions import CacheException
from ...config import settings


class FileCacheManager(CacheManager):
    """Файловый менеджер кэша"""
    
    def __init__(self, cache_dir: str = None):
        self.cache_dir = cache_dir or os.path.join(settings.base_dir, settings.cache_dir)
        self.metadata_file = os.path.join(self.cache_dir, "metadata.json")
        self._metadata: Dict[str, Dict] = {}
        self._lock = asyncio.Lock()
        
        # Создаем директорию
        os.makedirs(self.cache_dir, exist_ok=True)
        
        # Загружаем метаданные
        self._load_metadata()
    
    def _load_metadata(self):
        """Загрузить метаданные кэша"""
        if os.path.exists(self.metadata_file):
            try:
                with open(self.metadata_file, 'r') as f:
                    self._metadata = json.load(f)
                logger.info(f"Loaded cache metadata: {len(self._metadata)} entries")
            except Exception as e:
                logger.error(f"Failed to load cache metadata: {e}")
                self._metadata = {}
    
    def _save_metadata(self):
        """Сохранить метаданные кэша"""
        try:
            with open(self.metadata_file, 'w') as f:
                json.dump(self._metadata, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save cache metadata: {e}")
    
    def _get_cache_path(self, key: str) -> str:
        """Получить путь к файлу кэша"""
        return os.path.join(self.cache_dir, key)
    
    async def get(self, url: str, quality: Quality) -> Optional[DownloadResult]:
        """Получить из кэша"""
        async with self._lock:
            cache_key = self._get_key(url, quality)
            
            if cache_key not in self._metadata:
                return None
            
            meta = self._metadata[cache_key]
            file_path = meta.get('file_path')
            
            if not file_path or not os.path.exists(file_path):
                # Файл отсутствует, удаляем метаданные
                del self._metadata[cache_key]
                self._save_metadata()
                return None
            
            # Проверяем TTL
            created_at = datetime.fromisoformat(meta['created_at'])
            ttl = timedelta(hours=settings.cache_ttl_hours)
            if datetime.now() - created_at > ttl:
                await self.delete(url, quality)
                return None
            
            # Создаем объекты из метаданных
            from ..downloader.interfaces import MediaMetadata, MediaType
            
            metadata = MediaMetadata(
                url=meta['metadata']['url'],
                title=meta['metadata']['title'],
                author=meta['metadata']['author'],
                duration=meta['metadata']['duration'],
                size=meta['metadata'].get('size', 0),
                thumbnail_url=meta['metadata'].get('thumbnail_url'),
                media_type=MediaType(meta['metadata']['media_type']),
                quality=Quality(meta['metadata']['quality']) if meta['metadata'].get('quality') else None
            )
            
            return DownloadResult(
                file_path=file_path,
                metadata=metadata,
                from_cache=True
            )
    
    async def set(self, url: str, quality: Quality, result: DownloadResult):
        """Сохранить в кэш"""
        async with self._lock:
            cache_key = self._get_key(url, quality)
            
            # Копируем файл в кэш
            cache_path = self._get_cache_path(cache_key)
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            
            if result.file_path != cache_path:
                shutil.copy2(result.file_path, cache_path)
            
            # Сохраняем метаданные
            self._metadata[cache_key] = {
                'file_path': cache_path,
                'metadata': {
                    'url': result.metadata.url,
                    'title': result.metadata.title,
                    'author': result.metadata.author,
                    'duration': result.metadata.duration,
                    'size': result.metadata.size,
                    'thumbnail_url': result.metadata.thumbnail_url,
                    'media_type': result.metadata.media_type.value,
                    'quality': result.metadata.quality.value if result.metadata.quality else None
                },
                'created_at': datetime.now().isoformat(),
                'quality': quality.value
            }
            
            self._save_metadata()
            
            # Очищаем старые записи если превышен лимит
            await self._cleanup_if_needed()
    
    async def exists(self, url: str, quality: Quality) -> bool:
        """Проверить наличие в кэше"""
        result = await self.get(url, quality)
        return result is not None
    
    async def delete(self, url: str, quality: Quality):
        """Удалить из кэша"""
        async with self._lock:
            cache_key = self._get_key(url, quality)
            
            if cache_key in self._metadata:
                file_path = self._metadata[cache_key].get('file_path')
                if file_path and os.path.exists(file_path):
                    os.remove(file_path)
                
                del self._metadata[cache_key]
                self._save_metadata()
    
    async def get_stats(self) -> Dict:
        """Получить статистику кэша"""
        total_size = 0
        for meta in self._metadata.values():
            file_path = meta.get('file_path')
            if file_path and os.path.exists(file_path):
                total_size += os.path.getsize(file_path)
        
        return {
            'entries': len(self._metadata),
            'total_size_bytes': total_size,
            'total_size_mb': total_size / (1024 * 1024),
            'max_size_gb': settings.cache_max_size_gb,
            'cache_dir': self.cache_dir
        }
    
    async def _cleanup_if_needed(self):
        """Очистка старых записей при превышении лимита"""
        total_size = sum(
            os.path.getsize(meta['file_path'])
            for meta in self._metadata.values()
            if os.path.exists(meta['file_path'])
        )
        
        max_size = settings.cache_max_size_gb * 1024 * 1024 * 1024
        
        if total_size > max_size:
            # Сортируем по дате создания (старые первые)
            sorted_entries = sorted(
                self._metadata.items(),
                key=lambda x: x[1]['created_at']
            )
            
            # Удаляем старые пока не влезем в лимит
            for key, meta in sorted_entries:
                if total_size <= max_size:
                    break
                
                file_path = meta['file_path']
                if os.path.exists(file_path):
                    total_size -= os.path.getsize(file_path)
                    os.remove(file_path)
                
                del self._metadata[key]
            
            self._save_metadata()
    
    def _get_key(self, url: str, quality: Quality) -> str:
        """Сгенерировать ключ"""
        key = f"{url}:{quality.value}"
        return hashlib.md5(key.encode()).hexdigest()