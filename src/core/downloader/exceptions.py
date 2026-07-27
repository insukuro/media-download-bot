class DownloaderException(Exception):
    """Базовое исключение загрузчика"""
    pass


class InvalidURLException(DownloaderException):
    """Невалидный URL"""
    pass


class UnsupportedSourceException(DownloaderException):
    """Неподдерживаемый источник"""
    pass


class DownloadFailedException(DownloaderException):
    """Ошибка загрузки"""
    def __init__(self, message: str, url: str = None):
        self.url = url
        super().__init__(message)


class QualityNotAvailableException(DownloaderException):
    """Запрошенное качество недоступно"""
    pass


class CacheException(DownloaderException):
    """Ошибка кэша"""
    pass


class QueueFullException(DownloaderException):
    """Очередь переполнена"""
    pass