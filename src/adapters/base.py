# src/adapters/base.py
from abc import ABC, abstractmethod
from typing import Optional


class MessengerAdapter(ABC):
    """Базовый адаптер для мессенджеров"""
    
    @abstractmethod
    async def start(self):
        """Запуск адаптера"""
        pass
    
    @abstractmethod
    async def stop(self):
        """Остановка адаптера"""
        pass
    
    @abstractmethod
    async def send_message(
        self,
        chat_id: int,
        text: str,
        reply_markup=None,
        parse_mode: str = "HTML"
    ):
        """Отправить текстовое сообщение"""
        pass
    
    @abstractmethod
    async def send_media(
        self,
        chat_id: int,
        media_type: str,
        file_path: str,
        caption: Optional[str] = None,
        thumbnail: Optional[str] = None
    ):
        """Отправить медиафайл"""
        pass
    
    @abstractmethod
    async def send_photo(
        self,
        chat_id: int,
        photo_path: str,
        caption: Optional[str] = None
    ):
        """Отправить фото"""
        pass