from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import Column, Integer, String, DateTime, Float, Text
from datetime import datetime

from .config import settings


# Создаем движок
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug
)

# Фабрика сессий
async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)


class Base(DeclarativeBase):
    pass


class DownloadLog(Base):
    """Лог загрузок"""
    __tablename__ = "download_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(100), index=True)
    url = Column(Text)
    quality = Column(String(50))
    media_type = Column(String(50))
    status = Column(String(50))
    file_size = Column(Integer, default=0)
    from_cache = Column(Integer, default=0)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<DownloadLog {self.id} - {self.status}>"


class UserStats(Base):
    """Статистика пользователей"""
    __tablename__ = "user_stats"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(100), unique=True, index=True)
    total_downloads = Column(Integer, default=0)
    total_size = Column(Integer, default=0)
    last_download = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<UserStats {self.user_id} - {self.total_downloads} downloads>"


async def init_db():
    """Инициализация базы данных"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    """Получить сессию базы данных"""
    async with async_session() as session:
        yield session