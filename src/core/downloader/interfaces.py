from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Any
from datetime import datetime


class MediaType(str, Enum):
    VIDEO = "video"
    AUDIO = "audio"
    SHORTS = "shorts"
    PLAYLIST = "playlist"


class Quality(str, Enum):
    LOW = "360p"
    MEDIUM = "720p"
    HIGH = "1080p"
    AUDIO_LOW = "128kbps"
    AUDIO_MEDIUM = "192kbps"
    AUDIO_HIGH = "320kbps"


class DownloadStatus(str, Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CACHED = "cached"


@dataclass
class MediaMetadata:
    """Метаданные медиафайла"""
    url: str
    title: str
    author: str
    duration: int  # секунды
    size: int = 0  # байты
    thumbnail_url: Optional[str] = None
    media_type: MediaType = MediaType.VIDEO
    quality: Optional[Quality] = None
    formats: List[str] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def duration_formatted(self) -> str:
        minutes = self.duration // 60
        seconds = self.duration % 60
        return f"{minutes}:{seconds:02d}"
    
    @property
    def size_mb(self) -> float:
        return self.size / (1024 * 1024)


@dataclass
class DownloadResult:
    """Результат загрузки"""
    file_path: str
    metadata: MediaMetadata
    status: DownloadStatus = DownloadStatus.COMPLETED
    from_cache: bool = False
    downloaded_at: datetime = field(default_factory=datetime.now)
    error: Optional[str] = None


@dataclass
class DownloadTask:
    """Задача на загрузку"""
    id: str
    url: str
    media_type: MediaType
    quality: Quality
    user_id: str
    status: DownloadStatus = DownloadStatus.PENDING
    progress: float = 0.0
    created_at: datetime = field(default_factory=datetime.now)
    result: Optional[DownloadResult] = None


class SourceDownloader(ABC):
    """Базовый интерфейс для источников контента"""
    
    @abstractmethod
    async def validate_url(self, url: str) -> bool:
        """Проверка валидности URL"""
        pass
    
    @abstractmethod
    async def extract_metadata(self, url: str) -> MediaMetadata:
        """Извлечение метаданных"""
        pass
    
    @abstractmethod
    async def download(
        self, 
        url: str, 
        quality: Quality,
        progress_callback: Optional[callable] = None
    ) -> DownloadResult:
        """Загрузка медиафайла"""
        pass
    
    @abstractmethod
    async def get_available_qualities(self, url: str) -> List[Quality]:
        """Получить доступные качества"""
        pass
    
    async def get_playlist(
        self, 
        url: str, 
        limit: Optional[int] = None
    ) -> List[str]:
        """Получить список URL из плейлиста"""
        raise NotImplementedError("Playlist not supported")


class CacheManager(ABC):
    """Управление кэшем"""
    
    @abstractmethod
    async def get(self, url: str, quality: Quality) -> Optional[DownloadResult]:
        """Получить из кэша"""
        pass
    
    @abstractmethod
    async def set(self, url: str, quality: Quality, result: DownloadResult):
        """Сохранить в кэш"""
        pass
    
    @abstractmethod
    async def exists(self, url: str, quality: Quality) -> bool:
        """Проверить наличие в кэше"""
        pass
    
    @abstractmethod
    async def delete(self, url: str, quality: Quality):
        """Удалить из кэша"""
        pass
    
    @abstractmethod
    async def get_stats(self) -> Dict[str, Any]:
        """Получить статистику кэша"""
        pass


class DownloadQueue(ABC):
    """Очередь загрузок"""
    
    @abstractmethod
    async def enqueue(self, task: DownloadTask) -> str:
        """Добавить в очередь"""
        pass
    
    @abstractmethod
    async def dequeue(self) -> Optional[DownloadTask]:
        """Взять задачу из очереди"""
        pass
    
    @abstractmethod
    async def get_task(self, task_id: str) -> Optional[DownloadTask]:
        """Получить статус задачи"""
        pass
    
    @abstractmethod
    async def update_task(self, task: DownloadTask):
        """Обновить задачу"""
        pass
    
    @abstractmethod
    async def get_queue_size(self) -> int:
        """Размер очереди"""
        pass