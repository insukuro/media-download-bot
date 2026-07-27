import json
import os
from typing import Dict


class I18nLoader:
    """Загрузчик локализации"""
    
    def __init__(self, locales_dir: str = None):
        if locales_dir is None:
            locales_dir = os.path.join(os.path.dirname(__file__), "locales")
        
        self.locales_dir = locales_dir
        self.translations: Dict[str, Dict] = {}
        self._load_locales()
    
    def _load_locales(self):
        """Загрузить все файлы локализации"""
        if not os.path.exists(self.locales_dir):
            return
        
        for filename in os.listdir(self.locales_dir):
            if filename.endswith('.json'):
                locale = filename[:-5]  # Убираем .json
                filepath = os.path.join(self.locales_dir, filename)
                
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        self.translations[locale] = json.load(f)
                except Exception as e:
                    print(f"Error loading locale {locale}: {e}")
    
    def get_text(self, locale: str, key: str, default: str = None) -> str:
        """Получить текст по ключу"""
        # Пытаемся найти точную локаль
        if locale in self.translations and key in self.translations[locale]:
            return self.translations[locale][key]
        
        # Пытаемся найти основной язык (ru из ru-RU)
        main_locale = locale.split('-')[0] if '-' in locale else locale
        if main_locale in self.translations and key in self.translations[main_locale]:
            return self.translations[main_locale][key]
        
        # Fallback на английский
        if 'en' in self.translations and key in self.translations['en']:
            return self.translations['en'][key]
        
        # Возвращаем ключ или дефолтное значение
        return default or key


# Глобальный экземпляр
i18n = I18nLoader()