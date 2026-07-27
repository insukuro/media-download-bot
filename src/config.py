from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional
import os


class Settings(BaseSettings):
    # Application
    app_name: str = "MediaDownloader"
    debug: bool = Field(default=False)
    log_level: str = Field(default="INFO")
    
    # Paths
    base_dir: str = Field(default=os.path.dirname(os.path.dirname(__file__)))
    cache_dir: str = Field(default="cache")
    temp_dir: str = Field(default="temp")
    
    # Database
    database_url: str = Field(default="sqlite+aiosqlite:///database.db")
    redis_url: str = Field(default="redis://localhost:6379/0")
    
    # Cache
    cache_max_size_gb: int = Field(default=10)
    cache_ttl_hours: int = Field(default=72)
    
    # Queue
    max_concurrent_downloads: int = Field(default=2)
    queue_max_size: int = Field(default=100)
    download_timeout_seconds: int = Field(default=600)
    
    # Telegram
    telegram_token: str = Field(default="")
    telegram_admin_ids: list[int] = Field(default_factory=list)
    
    # VK
    vk_token: str = Field(default="")
    vk_group_id: int = Field(default=0)
    
    # Sources
    youtube_enabled: bool = Field(default=True)
    tiktok_enabled: bool = Field(default=True)
    
    # Limits
    max_file_size_mb: int = Field(default=50)
    max_video_duration_minutes: int = Field(default=60)
    
    # Locale
    default_locale: str = Field(default="ru")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()