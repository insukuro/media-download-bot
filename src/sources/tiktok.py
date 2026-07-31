# src/sources/tiktok.py (исправленная версия)
import asyncio
import os
import tempfile
import aiohttp
import re
from typing import List, Optional
from loguru import logger

from .base import BaseSourceDownloader
from ..core.downloader.interfaces import (
    MediaMetadata, DownloadResult, DownloadStatus,
    Quality, MediaType
)
from ..config import settings


class TikTokDownloader(BaseSourceDownloader):
    """Загрузчик TikTok"""
    
    def __init__(self):
        super().__init__()
        self.name = "tiktok"
        self.api_url = "https://tikwm.com/api/"
    
    async def validate_url(self, url: str) -> bool:
        """Проверить URL TikTok"""
        patterns = [
            r'tiktok\.com/@[\w.-]+/video/\d+',
            r'tiktok\.com/[\w.-]+/video/\d+',
            r'vm\.tiktok\.com/\w+',
            r'vt\.tiktok\.com/\w+',
        ]
        return any(re.search(pattern, url) for pattern in patterns)
    
    async def extract_metadata(self, url: str) -> MediaMetadata:
        """Извлечь метаданные TikTok видео"""
        try:
            # Очищаем URL от параметров
            clean_url = url.split('?')[0] if '?' in url else url
            
            async with aiohttp.ClientSession() as session:
                params = {'url': clean_url}
                async with session.get(self.api_url, params=params, timeout=30) as response:
                    if response.status != 200:
                        raise Exception(f"API returned status {response.status}")
                    
                    data = await response.json()
                    
                    if data.get('code') != 0:
                        raise Exception(f"TikTok API error: {data.get('msg', 'Unknown error')}")
                    
                    video_data = data.get('data', {})
                    if not video_data:
                        raise Exception("No video data in response")
                    
                    return MediaMetadata(
                        url=clean_url,
                        title=video_data.get('title', 'TikTok Video'),
                        author=video_data.get('author', {}).get('nickname', 'Unknown'),
                        duration=video_data.get('duration', 0),
                        size=0,  # Будет определено после скачивания
                        thumbnail_url=video_data.get('cover'),
                        media_type=MediaType.VIDEO,
                        extra={
                            'play_count': video_data.get('play_count'),
                            'digg_count': video_data.get('digg_count'),
                            'comment_count': video_data.get('comment_count'),
                        }
                    )
        except Exception as e:
            logger.error(f"Failed to extract TikTok metadata: {e}")
            raise
    
    async def download(
        self,
        url: str,
        quality: Quality,
        progress_callback=None  # Может быть None или callable
    ) -> DownloadResult:
        """Скачать TikTok видео без водяного знака"""
        temp_dir = tempfile.mkdtemp(dir=os.path.join(settings.base_dir, settings.temp_dir))
        
        try:
            # Очищаем URL
            clean_url = url.split('?')[0] if '?' in url else url
            
            async with aiohttp.ClientSession() as session:
                # Получаем информацию о видео
                params = {'url': clean_url}
                async with session.get(self.api_url, params=params, timeout=30) as response:
                    if response.status != 200:
                        raise Exception(f"API returned status {response.status}")
                    
                    data = await response.json()
                    
                    if data.get('code') != 0:
                        raise Exception(f"TikTok API error: {data.get('msg')}")
                    
                    video_data = data.get('data', {})
                    
                    # Выбираем видео без водяного знака
                    video_url = video_data.get('play')  # Без водяного знака
                    if not video_url:
                        video_url = video_data.get('wmplay')  # С водяным знаком как fallback
                    
                    if not video_url:
                        raise Exception("No video URL found in response")
                    
                    # Скачиваем видео
                    filename = f"tiktok_{video_data.get('video_id', 'unknown')}.mp4"
                    filepath = os.path.join(temp_dir, filename)
                    
                    async with session.get(video_url, timeout=300) as video_response:
                        if video_response.status != 200:
                            raise Exception(f"Video download failed with status {video_response.status}")
                        
                        total_size = int(video_response.headers.get('content-length', 0))
                        downloaded = 0
                        
                        with open(filepath, 'wb') as f:
                            async for chunk in video_response.content.iter_chunked(8192):
                                f.write(chunk)
                                downloaded += len(chunk)
                                
                                # Безопасный вызов progress_callback
                                if progress_callback and total_size > 0:
                                    percent = (downloaded / total_size) * 100
                                    try:
                                        progress_callback(percent)  # Не await! Это синхронный коллбэк
                                    except Exception as e:
                                        logger.debug(f"Progress callback error: {e}")
                    
                    # Проверяем что файл скачался
                    if not os.path.exists(filepath) or os.path.getsize(filepath) == 0:
                        raise Exception("Downloaded file is empty or missing")
                    
                    # Создаем метаданные
                    metadata = await self.extract_metadata(clean_url)
                    metadata.quality = quality
                    metadata.size = os.path.getsize(filepath)
                    
                    return DownloadResult(
                        file_path=filepath,
                        metadata=metadata,
                        status=DownloadStatus.COMPLETED
                    )
                    
        except Exception as e:
            logger.error(f"TikTok download failed: {e}")
            raise
    
    async def get_available_qualities(self, url: str) -> List[Quality]:
        """TikTok поддерживает только одно качество"""
        return [Quality.HIGH]