import asyncio
import os
import tempfile
from typing import List, Optional
from loguru import logger
import yt_dlp

from .base import BaseSourceDownloader
from ..core.downloader.interfaces import (
    MediaMetadata, DownloadResult, DownloadStatus,
    Quality, MediaType
)
from ..config import settings


class YouTubeDownloader(BaseSourceDownloader):
    """Загрузчик YouTube"""
    
    def __init__(self):
        super().__init__()
        self.name = "youtube"
    
    async def validate_url(self, url: str) -> bool:
        """Проверить URL YouTube"""
        return any(domain in url for domain in [
            "youtube.com/watch",
            "youtu.be/",
            "youtube.com/shorts",
            "youtube.com/playlist"
        ])
    
    async def extract_metadata(self, url: str) -> MediaMetadata:
        """Извлечь метаданные видео"""
        try:
            loop = asyncio.get_event_loop()
            
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
            }
            
            def extract():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return ydl.extract_info(url, download=False)
            
            info = await loop.run_in_executor(None, extract)
            
            # Определяем тип
            media_type = MediaType.VIDEO
            if info.get('duration', 0) <= 60:  # Shorts обычно до 60 секунд
                if 'shorts' in url:
                    media_type = MediaType.SHORTS
            
            return MediaMetadata(
                url=url,
                title=info.get('title', 'Unknown'),
                author=info.get('uploader', 'Unknown'),
                duration=info.get('duration', 0),
                size=info.get('filesize') or 0,
                thumbnail_url=info.get('thumbnail'),
                media_type=media_type,
                extra={
                    'view_count': info.get('view_count'),
                    'like_count': info.get('like_count'),
                    'upload_date': info.get('upload_date'),
                }
            )
        except Exception as e:
            logger.error(f"Failed to extract metadata: {e}")
            raise
    
    async def download(
        self,
        url: str,
        quality: Quality,
        progress_callback: Optional[callable] = None
    ) -> DownloadResult:
        """Скачать видео с YouTube"""
        temp_dir = tempfile.mkdtemp(dir=os.path.join(settings.base_dir, settings.temp_dir))
        
        try:
            # Определяем формат
            format_selectors = {
                Quality.LOW: 'best[height<=360]/best',
                Quality.MEDIUM: 'best[height<=720]/best',
                Quality.HIGH: 'best[height<=1080]/best',
                Quality.AUDIO_LOW: 'bestaudio[abr<=128]/bestaudio',
                Quality.AUDIO_MEDIUM: 'bestaudio[abr<=192]/bestaudio',
                Quality.AUDIO_HIGH: 'bestaudio[abr<=320]/bestaudio',
            }
            
            is_audio = quality in [Quality.AUDIO_LOW, Quality.AUDIO_MEDIUM, Quality.AUDIO_HIGH]
            
            # Прогресс хук
            def progress_hook(d):
                if progress_callback and d['status'] == 'downloading':
                    total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                    downloaded = d.get('downloaded_bytes', 0)
                    if total > 0:
                        percent = (downloaded / total) * 100
                        asyncio.create_task(progress_callback(percent))
            
            ydl_opts = {
                'format': format_selectors.get(quality, 'best'),
                'outtmpl': os.path.join(temp_dir, '%(title)s.%(ext)s'),
                'progress_hooks': [progress_hook],
                'quiet': True,
                'no_warnings': True,
            }
            
            if is_audio:
                ydl_opts['postprocessors'] = [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': quality.value.replace('kbps', ''),
                }]
            
            # Загружаем
            loop = asyncio.get_event_loop()
            
            def download_video():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    filename = ydl.prepare_filename(info)
                    if is_audio:
                        filename = filename.rsplit('.', 1)[0] + '.mp3'
                    return info, filename
            
            info, filename = await loop.run_in_executor(None, download_video)
            
            # Создаем метаданные
            metadata = await self.extract_metadata(url)
            metadata.quality = quality
            metadata.size = os.path.getsize(filename)
            
            return DownloadResult(
                file_path=filename,
                metadata=metadata,
                status=DownloadStatus.COMPLETED
            )
            
        except Exception as e:
            logger.error(f"Download failed: {e}")
            raise
        finally:
            # Очистка временных файлов (кроме скачанного)
            pass
    
    async def get_playlist(self, url: str, limit: Optional[int] = None) -> List[str]:
        """Получить список видео из плейлиста"""
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
        }
        
        loop = asyncio.get_event_loop()
        
        def extract_playlist():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if 'entries' in info:
                    entries = info['entries']
                    if limit:
                        entries = entries[:limit]
                    return [
                        f"https://youtube.com/watch?v={entry['id']}"
                        for entry in entries
                        if entry.get('id')
                    ]
                return []
        
        return await loop.run_in_executor(None, extract_playlist)
    
    async def get_available_qualities(self, url: str) -> List[Quality]:
        """Получить доступные качества"""
        try:
            info = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: yt_dlp.YoutubeDL({'quiet': True}).extract_info(url, download=False)
            )
            
            formats = info.get('formats', [])
            available = set()
            
            for f in formats:
                height = f.get('height')
                if height:
                    if height <= 360:
                        available.add(Quality.LOW)
                    if height <= 720:
                        available.add(Quality.MEDIUM)
                    if height <= 1080:
                        available.add(Quality.HIGH)
                
                abr = f.get('abr')
                if abr:
                    abr = int(abr)
                    if abr <= 128:
                        available.add(Quality.AUDIO_LOW)
                    if abr <= 192:
                        available.add(Quality.AUDIO_MEDIUM)
                    if abr <= 320:
                        available.add(Quality.AUDIO_HIGH)
            
            return sorted(available, key=lambda q: q.value)
        except:
            return list(Quality)