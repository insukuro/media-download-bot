import asyncio
from collections import deque
from typing import Dict, Optional
from datetime import datetime
from loguru import logger

from ..downloader.interfaces import DownloadQueue, DownloadTask, DownloadStatus
from ..downloader.exceptions import QueueFullException
from ...config import settings


class AsyncDownloadQueue(DownloadQueue):
    """Асинхронная очередь загрузок"""
    
    def __init__(self, max_size: int = None):
        self.max_size = max_size or settings.queue_max_size
        self._queue: deque[DownloadTask] = deque()
        self._tasks: Dict[str, DownloadTask] = {}
        self._lock = asyncio.Lock()
        self._completion_events: Dict[str, asyncio.Event] = {}
    
    async def enqueue(self, task: DownloadTask) -> str:
        """Добавить в очередь"""
        async with self._lock:
            if len(self._queue) >= self.max_size:
                raise QueueFullException(f"Queue is full (max: {self.max_size})")
            
            self._queue.append(task)
            self._tasks[task.id] = task
            self._completion_events[task.id] = asyncio.Event()
            
            logger.info(f"Task enqueued: {task.id}, queue size: {len(self._queue)}")
            return task.id
    
    async def dequeue(self) -> Optional[DownloadTask]:
        """Взять задачу из очереди"""
        async with self._lock:
            if self._queue:
                task = self._queue.popleft()
                logger.info(f"Task dequeued: {task.id}, queue size: {len(self._queue)}")
                return task
            return None
    
    async def get_task(self, task_id: str) -> Optional[DownloadTask]:
        """Получить статус задачи"""
        return self._tasks.get(task_id)
    
    async def update_task(self, task: DownloadTask):
        """Обновить задачу"""
        async with self._lock:
            self._tasks[task.id] = task
            
            # Если задача завершена, уведомляем ожидающих
            if task.status in [DownloadStatus.COMPLETED, DownloadStatus.FAILED]:
                event = self._completion_events.get(task.id)
                if event:
                    event.set()
    
    async def wait_for_completion(self, task_id: str, timeout: int = None) -> DownloadTask:
        """Ждать завершения задачи"""
        timeout = timeout or settings.download_timeout_seconds
        
        event = self._completion_events.get(task_id)
        if not event:
            raise ValueError(f"Task {task_id} not found")
        
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            task = await self.get_task(task_id)
            if task:
                task.status = DownloadStatus.FAILED
                await self.update_task(task)
            raise TimeoutError(f"Download timeout for task {task_id}")
        
        return await self.get_task(task_id)
    
    async def get_queue_size(self) -> int:
        """Размер очереди"""
        return len(self._queue)
    
    async def get_all_tasks(self) -> Dict[str, DownloadTask]:
        """Получить все задачи"""
        return self._tasks.copy()
    
    async def clear_completed(self):
        """Очистить завершенные задачи"""
        async with self._lock:
            completed_ids = [
                task_id for task_id, task in self._tasks.items()
                if task.status in [DownloadStatus.COMPLETED, DownloadStatus.FAILED]
            ]
            for task_id in completed_ids:
                del self._tasks[task_id]
                del self._completion_events[task_id]