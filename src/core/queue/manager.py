# src/core/queue/manager.py
import asyncio
from collections import deque
from typing import Dict, Optional, List
from datetime import datetime
from loguru import logger

from ..downloader.interfaces import DownloadQueue, DownloadTask, DownloadStatus
from ..downloader.exceptions import QueueFullException
from ...config import settings


class AsyncDownloadQueue(DownloadQueue):
    """Асинхронная очередь загрузок с поддержкой приоритетов"""
    
    def __init__(self, max_size: int = None):
        self.max_size = max_size or settings.queue_max_size
        self._queue: deque[DownloadTask] = deque()
        self._active_tasks: Dict[str, DownloadTask] = {}
        self._completed_tasks: Dict[str, DownloadTask] = {}
        self._lock = asyncio.Lock()
        self._completion_events: Dict[str, asyncio.Event] = {}
        self._task_updated = asyncio.Condition(self._lock)  # Для уведомления воркеров
        
        # Статистика
        self._total_processed = 0
        self._total_errors = 0
    
    async def enqueue(self, task: DownloadTask) -> str:
        """Добавить в очередь с проверкой дубликатов"""
        async with self._lock:
            # Проверяем, нет ли уже такой задачи
            for t in self._queue:
                if t.url == task.url and t.quality == task.quality and t.status == DownloadStatus.PENDING:
                    logger.info(f"Duplicate task detected: {task.url}")
                    return t.id
            
            if len(self._queue) >= self.max_size:
                raise QueueFullException(f"Queue is full (max: {self.max_size})")
            
            self._queue.append(task)
            self._completion_events[task.id] = asyncio.Event()
            
            # Уведомляем воркеров о новой задаче
            self._task_updated.notify()
            
            logger.info(f"Task enqueued: {task.id}, queue size: {len(self._queue)}, "
                       f"active: {len(self._active_tasks)}")
            return task.id
    
    async def dequeue(self) -> Optional[DownloadTask]:
        """Взять задачу из очереди (блокирующий вызов для воркеров)"""
        async with self._lock:
            # Ждем, пока появится задача или таймаут
            while not self._queue:
                try:
                    # Ждем с таймаутом, чтобы можно было graceful shutdown
                    await asyncio.wait_for(
                        self._task_updated.wait(),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue
                except asyncio.CancelledError:
                    return None
            
            task = self._queue.popleft()
            task.status = DownloadStatus.DOWNLOADING
            task.started_at = datetime.now()
            self._active_tasks[task.id] = task
            
            logger.info(f"Task dequeued: {task.id}, remaining: {len(self._queue)}, "
                       f"active: {len(self._active_tasks)}")
            return task
    
    async def get_task(self, task_id: str) -> Optional[DownloadTask]:
        """Получить статус задачи"""
        # Проверяем во всех состояниях
        for task_dict in [self._active_tasks, self._completed_tasks]:
            if task_id in task_dict:
                return task_dict[task_id]
        
        # Проверяем в очереди
        async with self._lock:
            for task in self._queue:
                if task.id == task_id:
                    return task
        
        return None
    
    async def update_task(self, task: DownloadTask):
        """Обновить задачу"""
        async with self._lock:
            if task.status in [DownloadStatus.COMPLETED, DownloadStatus.FAILED]:
                # Перемещаем в завершенные
                self._active_tasks.pop(task.id, None)
                self._completed_tasks[task.id] = task
                
                if task.status == DownloadStatus.COMPLETED:
                    self._total_processed += 1
                else:
                    self._total_errors += 1
                
                # Уведомляем ожидающих
                event = self._completion_events.get(task.id)
                if event:
                    event.set()
            else:
                # Обновляем в активных
                if task.id in self._active_tasks:
                    self._active_tasks[task.id] = task
    
    async def wait_for_completion(self, task_id: str, timeout: int = None) -> DownloadTask:
        """Ждать завершения задачи с прогрессом"""
        timeout = timeout or settings.download_timeout_seconds
        
        event = self._completion_events.get(task_id)
        if not event:
            # Может быть уже завершена
            task = await self.get_task(task_id)
            if task and task.status in [DownloadStatus.COMPLETED, DownloadStatus.FAILED]:
                return task
            raise ValueError(f"Task {task_id} not found")
        
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            task = await self.get_task(task_id)
            if task:
                task.status = DownloadStatus.FAILED
                task.error = f"Timeout after {timeout}s"
                await self.update_task(task)
            raise TimeoutError(f"Download timeout for task {task_id}")
        
        return await self.get_task(task_id)
    
    async def get_queue_size(self) -> int:
        """Размер очереди"""
        return len(self._queue)
    
    async def get_active_count(self) -> int:
        """Количество активных загрузок"""
        return len(self._active_tasks)
    
    async def get_stats(self) -> Dict:
        """Статистика очереди"""
        return {
            'queue_size': len(self._queue),
            'active_downloads': len(self._active_tasks),
            'completed_downloads': len(self._completed_tasks),
            'total_processed': self._total_processed,
            'total_errors': self._total_errors,
            'max_size': self.max_size
        }
    
    async def clear_completed(self, max_age_hours: int = 24):
        """Очистить старые завершенные задачи"""
        async with self._lock:
            now = datetime.now()
            to_delete = []
            
            for task_id, task in self._completed_tasks.items():
                if task.completed_at:
                    age = now - task.completed_at
                    if age.total_seconds() > max_age_hours * 3600:
                        to_delete.append(task_id)
            
            for task_id in to_delete:
                del self._completed_tasks[task_id]
                self._completion_events.pop(task_id, None)
            
            if to_delete:
                logger.info(f"Cleared {len(to_delete)} old completed tasks")
    
    async def cancel_task(self, task_id: str) -> bool:
        """Отменить задачу"""
        async with self._lock:
            # Проверяем в очереди
            for i, task in enumerate(self._queue):
                if task.id == task_id:
                    task.status = DownloadStatus.FAILED
                    task.error = "Cancelled by user"
                    self._queue.remove(task)
                    self._completed_tasks[task_id] = task
                    
                    event = self._completion_events.get(task_id)
                    if event:
                        event.set()
                    
                    return True
            
            # Проверяем в активных
            if task_id in self._active_tasks:
                task = self._active_tasks[task_id]
                task.status = DownloadStatus.FAILED
                task.error = "Cancelled by user"
                # Не можем реально отменить загрузку, но помечаем
                
                event = self._completion_events.get(task_id)
                if event:
                    event.set()
                
                return True
        
        return False