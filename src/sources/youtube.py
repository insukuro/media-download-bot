# src/sources/youtube.py
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
                'skip_download': True,
                'no_check_formats': True,
                'extractor_args': {'youtube': {'skip': ['dash', 'hls']}},  # 🔥 ПРОПУСКАЕМ DASH/HLS
                'youtube_include_dash_manifest': False,  # 🔥 НЕ ЗАГРУЖАЕМ МАНИФЕСТ
                'format': 'best[height<=1080]/best',  # 🔥 ЯВНО УКАЗЫВАЕМ ФОРМАТ
                'format_sort': ['res:1080', 'codec:h264'],  # 🔥 СОРТИРОВКА ФОРМАТОВ
                'noplaylist': True,
                'no_color': True,
                'socket_timeout': 10,
                'retries': 3,
            }
            
            def extract():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    try:
                        return ydl.extract_info(url, download=False)
                    except Exception as e:
                        # Пробуем еще раз с минимальными настройками
                        logger.warning(f"First attempt failed: {e}, trying minimal opts")
                        ydl_opts_min = {
                            'quiet': True,
                            'no_warnings': True,
                            'skip_download': True,
                            'extract_flat': True,  # 🔥 ПЛОСКОЕ ИЗВЛЕЧЕНИЕ
                        }
                        with yt_dlp.YoutubeDL(ydl_opts_min) as ydl2:
                            return ydl2.extract_info(url, download=False)
            
            info = await loop.run_in_executor(None, extract)
            
            # Если extract_flat, то дополняем информацию
            if info.get('duration') is None:
                # Пробуем получить больше инфы
                try:
                    ydl_opts_full = {
                        'quiet': True,
                        'skip_download': True,
                        'extract_flat': False,
                        'no_check_formats': True,
                        'format': 'best',
                    }
                    with yt_dlp.YoutubeDL(ydl_opts_full) as ydl:
                        info = ydl.extract_info(url, download=False)
                except:
                    pass
            
            # Определяем тип
            media_type = MediaType.VIDEO
            duration = info.get('duration', 0) or 0
            if duration <= 60:
                if 'shorts' in url.lower() or 'short' in str(info.get('webpage_url', '')).lower():
                    media_type = MediaType.SHORTS
            
            return MediaMetadata(
                url=url,
                title=info.get('title', 'Unknown'),
                author=info.get('uploader', 'Unknown'),
                duration=duration,
                size=info.get('filesize') or info.get('filesize_approx') or 0,
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
            # 🔥 ПОСЛЕДНЯЯ ПОПЫТКА - только базовая инфа
            try:
                ydl_opts_last = {
                    'quiet': True,
                    'extract_flat': True,
                    'skip_download': True,
                }
                with yt_dlp.YoutubeDL(ydl_opts_last) as ydl:
                    info = ydl.extract_info(url, download=False)
                return MediaMetadata(
                    url=url,
                    title=info.get('title', 'Unknown'),
                    author=info.get('uploader', 'Unknown'),
                    duration=info.get('duration', 0) or 0,
                    size=0,
                    thumbnail_url=info.get('thumbnail'),
                    media_type=MediaType.VIDEO,
                    extra={}
                )
            except Exception as e2:
                logger.error(f"Final attempt failed: {e2}")
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
            is_audio = quality in [Quality.AUDIO_LOW, Quality.AUDIO_MEDIUM, Quality.AUDIO_HIGH]
            
            # Прогресс хук
            def progress_hook(d):
                if progress_callback and d['status'] == 'downloading':
                    total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                    downloaded = d.get('downloaded_bytes', 0)
                    if total > 0:
                        percent = (downloaded / total) * 100
                        asyncio.create_task(progress_callback(percent))
            
            if is_audio:
                format_selectors = {
                    Quality.AUDIO_LOW: 'worstaudio[ext=m4a]/worstaudio[ext=mp4]/worstaudio',
                    Quality.AUDIO_MEDIUM: 'bestaudio[ext=m4a]/bestaudio[ext=mp4]/bestaudio',
                    Quality.AUDIO_HIGH: 'bestaudio/best',
                }
            else:
                format_selectors = {
                    Quality.LOW: 'worstvideo[height<=360]+bestaudio/worst[height<=360]/worst',
                    Quality.MEDIUM: 'bestvideo[height<=720]+bestaudio/best[height<=720]/best',
                    Quality.HIGH: 'bestvideo[height<=1080]+bestaudio/best[height<=1080]/best',
                }
                        
            ydl_opts = {
                'format': format_selectors.get(quality, 'best'),
                'outtmpl': os.path.join(temp_dir, '%(title)s.%(ext)s'),
                'progress_hooks': [progress_hook],
                'quiet': True,
                'no_warnings': True,
                'ignoreerrors': False,
                'no_color': True,
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
                        # Меняем расширение если аудио
                        base = os.path.splitext(filename)[0]
                        filename = base + '.mp3'
                    return info, filename
            
            info, filename = await loop.run_in_executor(None, download_video)
            
            # Проверяем что файл существует
            if not os.path.exists(filename):
                # Может быть другое расширение
                possible_files = os.listdir(temp_dir)
                if possible_files:
                    filename = os.path.join(temp_dir, possible_files[0])
            
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
    
    async def get_playlist(self, url: str, limit: Optional[int] = None) -> List[str]:
        """Получить список видео из плейлиста"""
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'skip_download': True,
            'no_check_formats': True,
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
            ydl_opts = {
                'quiet': True,
                'skip_download': True,
                'no_check_formats': True,
            }
            
            loop = asyncio.get_event_loop()
            
            def extract_info():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return ydl.extract_info(url, download=False)
            
            info = await loop.run_in_executor(None, extract_info)
            
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
            
            # Аудио всегда доступно
            available.update([Quality.AUDIO_LOW, Quality.AUDIO_MEDIUM, Quality.AUDIO_HIGH])
            
            return sorted(available, key=lambda q: q.value)
        except Exception as e:
            logger.warning(f"Failed to get qualities, returning all: {e}")
            return list(Quality)