# src/core/cache/file_id_cache.py
import json
import hashlib
from typing import Optional
from loguru import logger
import redis.asyncio as aioredis

from ..downloader.interfaces import Quality
from ...config import settings


class FileIdCache:
    """Кэш Telegram file_id в Redis для мгновенной отправки"""

    def __init__(self, redis_client: aioredis.Redis = None):
        self.redis = redis_client
        self._prefix = "file_id:"
        self._ttl = settings.cache_ttl_hours * 3600

    async def _get_redis(self) -> aioredis.Redis:
        if not self.redis:
            self.redis = aioredis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True
            )
        return self.redis

    def _make_key(self, url: str, quality: Quality) -> str:
        raw = f"{url}:{quality.value}"
        return f"{self._prefix}{hashlib.md5(raw.encode()).hexdigest()}"

    async def get(self, url: str, quality: Quality) -> Optional[dict]:
        try:
            r = await self._get_redis()
            key = self._make_key(url, quality)
            data = await r.get(key)
            if data:
                logger.info(f"FileId cache hit: {url}")
                return json.loads(data)
        except Exception as e:
            logger.error(f"Failed to get file_id from cache: {e}")
        return None

    # В методе set добавить caption
    async def set(self, url: str, quality: Quality, file_id: str, media_type: str, caption: str = None):
        try:
            r = await self._get_redis()
            key = self._make_key(url, quality)
            value = json.dumps({
                'file_id': file_id,
                'media_type': media_type,
                'caption': caption
            })
            await r.setex(key, self._ttl, value)
            logger.info(f"FileId cached: {url} -> {file_id}")
        except Exception as e:
            logger.error(f"Failed to set file_id cache: {e}")

    async def exists(self, url: str, quality: Quality) -> bool:
        try:
            r = await self._get_redis()
            key = self._make_key(url, quality)
            return await r.exists(key) > 0
        except Exception as e:
            logger.error(f"Failed to check file_id cache: {e}")
            return False

    async def delete(self, url: str, quality: Quality):
        try:
            r = await self._get_redis()
            key = self._make_key(url, quality)
            await r.delete(key)
        except Exception as e:
            logger.error(f"Failed to delete file_id cache: {e}")

    async def get_cached_qualities(self, url: str) -> list:
        """Возвращает список качеств, для которых есть file_id"""
        try:
            r = await self._get_redis()
            pattern = f"{self._prefix}{hashlib.md5(url.encode()).hexdigest()}:*"
            # Упрощённо: проверяем все известные качества
            cached = []
            for quality in Quality:
                if await self.exists(url, quality):
                    cached.append(quality)
            return cached
        except Exception as e:
            logger.error(f"Failed to get cached qualities: {e}")
            return []