# MediaDownloader

Многоплатформенный бот для скачивания медиа с поддержкой YouTube, TikTok и других платформ.

## Возможности

- 📹 Скачивание видео с YouTube в различных качествах
- 🎵 Извлечение аудио (MP3) из видео
- 🎬 Поддержка YouTube Shorts
- 🎵 Скачивание TikTok без водяного знака
- 💾 Умное кэширование
- 🌍 Мультиязычность (Русский, English)
- 📊 Админ-панель со статистикой
- 🔄 Очередь загрузок для защиты от перегрузок

## Быстрый старт

Клонируйте репозиторий:
```bash
git clone https://github.com/yourusername/MediaDownloader.git
cd MediaDownloader
```
Создайте файл .env на основе .env.example:

```bash
cp .env.example .env```
Заполните необходимые переменные (TELEGRAM_TOKEN обязательно)

Запустите через Docker Compose:

```bash
docker-compose up -d
```
Или локально:

bash
pip install -r requirements.txt
python -m src.main
Архитектура
Проект построен как модульный монолит с четким разделением ответственности:

Core - ядро приложения (загрузка, кэш, очередь)

Sources - источники контента (YouTube, TikTok)

Adapters - адаптеры мессенджеров (Telegram, VK)

Capabilities - слой возможностей адаптеров

Admin - админ-панель

i18n - интернационализация

Добавление новых источников
Создайте класс в src/sources/

Наследуйте от BaseSourceDownloader

Реализуйте необходимые методы

Зарегистрируйте в src/main.py


```
media-download-bot
├─ Dockerfile.yml
├─ README.md
├─ docker-compose.yml
├─ pyproject.toml
├─ requirements.txt
└─ src
   ├─ __init__.py
   ├─ adapters
   │  ├─ __init__.py
   │  ├─ base.py
   │  ├─ telegram
   │  │  ├─ __init__.py
   │  │  ├─ adapter.py
   │  │  └─ handlers.py
   │  └─ vk
   │     └─ __init__.py
   ├─ admin
   │  └─ __init__.py
   ├─ capabilities
   │  └─ __init__.py
   ├─ config.py
   ├─ core
   │  ├─ __init__.py
   │  ├─ cache
   │  │  ├─ __init__.py
   │  │  └─ manager.py
   │  ├─ downloader
   │  │  ├─ __init__.py
   │  │  ├─ exceptions.py
   │  │  ├─ interfaces.py
   │  │  └─ service.py
   │  └─ queue
   │     ├─ __init__.py
   │     └─ manager.py
   ├─ database.py
   ├─ i18n
   │  ├─ __init__.py
   │  ├─ loader.py
   │  └─ locales
   │     ├─ en.json
   │     └─ ru.json
   ├─ main.py
   └─ sources
      ├─ __init__.py
      ├─ base.py
      ├─ tiktok.py
      └─ youtube.py

```