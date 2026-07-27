# src/sources/base.py
from abc import ABC, abstractmethod
from typing import List
from ..core.downloader.interfaces import SourceDownloader, Quality


class BaseSourceDownloader(SourceDownloader, ABC):
    """Базовый класс для источников"""
    
    def __init__(self):
        self.name = "base"
    
    @abstractmethod
    async def validate_url(self, url: str) -> bool:
        pass
    
    async def get_available_qualities(self, url: str) -> List[Quality]:
        """По умолчанию возвращаем все качества"""
        return [
            Quality.LOW, Quality.MEDIUM, Quality.HIGH,
            Quality.AUDIO_LOW, Quality.AUDIO_MEDIUM, Quality.AUDIO_HIGH
        ]