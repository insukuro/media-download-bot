# src/core/url_storage.py
import os
import json
import hashlib
from datetime import datetime, timedelta
from loguru import logger
from typing import Dict, Optional

from ..config import settings


class UrlStorage:
    """Временное хранилище URL с автоочисткой (общее для всех адаптеров)"""
    
    def __init__(self, storage_file: Optional[str] = None):
        self.storage_file = storage_file or os.path.join(settings.base_dir, "url_storage.json")
        self._data: Dict[str, dict] = {}
        self._load()
    
    def _load(self):
        try:
            if os.path.exists(self.storage_file):
                with open(self.storage_file, 'r') as f:
                    self._data = json.load(f)
                logger.info(f"Loaded URL storage: {len(self._data)} entries")
        except Exception as e:
            logger.warning(f"Failed to load URL storage: {e}")
            self._data = {}
    
    def _save(self):
        try:
            with open(self.storage_file, 'w') as f:
                json.dump(self._data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save URL storage: {e}")
    
    def store(self, url: str) -> str:
        """Сохранить URL и вернуть короткий ключ"""
        # Очищаем URL от параметров для ключа
        clean_url = url.split('?')[0] if '?' in url else url
        key = hashlib.md5(clean_url.encode()).hexdigest()[:8]
        self._data[key] = {
            'url': clean_url,
            'created_at': datetime.now().isoformat()
        }
        self._save()
        return key
    
    def get(self, key: str) -> str:
        """Получить URL по ключу. Если не найден, возвращает сам ключ (для совместимости)"""
        data = self._data.get(key)
        if data:
            return data['url']
        logger.warning(f"URL key not found: {key}")
        return key  # fallback
    
    def cleanup(self, max_age_hours: int = 24):
        """Очистить старые записи"""
        now = datetime.now()
        to_delete = []
        for key, data in self._data.items():
            created = datetime.fromisoformat(data['created_at'])
            if now - created > timedelta(hours=max_age_hours):
                to_delete.append(key)
        
        for key in to_delete:
            del self._data[key]
        
        if to_delete:
            self._save()
            logger.info(f"Cleaned up {len(to_delete)} old URL entries")