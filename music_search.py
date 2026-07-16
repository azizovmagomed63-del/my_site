"""
Поиск музыки в Telegram с помощью Telethon.

Скрипт умеет:
  1. Искать аудиофайлы (музыку) по текстовому запросу в конкретном чате/канале
     или во всех диалогах сразу.
  2. Скачивать найденные треки в папку downloads/.

Установка зависимостей:
    pip install telethon

Перед запуском получите api_id и api_hash на https://my.telegram.org
(раздел "API development tools").

Запуск:
    python telegram_music_search.py "название песни"
    python telegram_music_search.py "название песни" --chat @some_music_channel
    python telegram_music_search.py "название песни" --all-dialogs --download
"""

import argparse
import asyncio
import os

from telethon import TelegramClient
from telethon.tl.types import (
    InputMessagesFilterMusic,
    DocumentAttributeAudio,
)

# ==== Заполните своими данными или задайте через переменные окружения ====
API_ID = int(os.environ.get("TG_API_ID", "0"))
API_HASH = os.environ.get("TG_API_HASH", "")
SESSION_NAME = "music_search_session"
DOWNLOAD_DIR = "downloads"
# ===========================================================================


def format_track(message) -> str:
    """Формирует человекочитаемое описание найденного трека."""
    audio = message.audio
    performer, title = None, None

    if audio:
        for attr in audio.attributes:
            if isinstance(attr, DocumentAttributeAudio):
                performer = attr.performer
                title = attr.title

    name = " - ".join(filter(None, [performer, title])) or (message.file.name if message.file else "audio")
    duration = f"{audio.attributes[0].duration}s" if audio and audio.attributes else "?"
    chat_title = getattr(message.chat, "title", None) or getattr(message.chat, "first_name", "Saved Messages")

    return f"[{message.id}] {name} ({duration}) — {chat_title} — {message.date:%Y-%m-%d}"


async def search_in_chat(client: TelegramClient, chat, query: str, limit: int):
    """Ищет музыку по запросу в одном чате/канале."""
    results = []
    async for message in client.iter_messages(
        chat,
        search=query,
        filter=InputMessagesFilterMusic,
        limit=limit,
    ):
        if message.audio:
            results.append(message)
    return results


async def search_all_dialogs(client: TelegramClient, query: str, limit_per_chat: int):
    """Ищет музыку по запросу во всех диалогах пользователя."""
    all_results = []
    async for dialog in client.iter_dialogs():
        try:
            found = await search_in_chat(client, dialog.entity, query, limit_per_chat)
        except Exception as e:
            print(f"  Пропускаю '{dialog.name}': {e}")
            continue
        if found:
            print(f"  Найдено {len(found)} треков в '{dialog.name}'")
            all_results.extend(found)
    return all_results


async def download_tracks(client: TelegramClient, messages):
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    for message in messages:
        print(f"Скачиваю: {format_track(message)}")
        path = await message.download_media(file=DOWNLOAD_DIR)
        print(f"  -> {path}")


async def main():
    parser = argparse.ArgumentParser(description="Поиск музыки в Telegram через Telethon")
    parser.add_argument("query", help="Текст запроса (название трека/исполнитель)")
    parser.add_argument(
        "--chat",
        help="Username, ID или ссылка на чат/канал для поиска (по умолчанию — Избранное/Saved Messages)",
        default="me",
    )
    parser.add_argument(
        "--all-dialogs",
        action="store_true",
        help="Искать во всех диалогах, а не в одном чате",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Максимум результатов на один чат (по умолчанию 50)",
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="Скачать найденные треки в папку downloads/",
    )
    args = parser.parse_args()

    if not API_ID or not API_HASH:
        raise SystemExit(
            "Не заданы TG_API_ID / TG_API_HASH. "
            "Получите их на https://my.telegram.org и задайте как переменные окружения "
            "или впишите прямо в скрипт (API_ID, API_HASH)."
        )

    async with TelegramClient(SESSION_NAME, API_ID, API_HASH) as client:
        print(f"Ищу '{args.query}'...")

        if args.all_dialogs:
            results = await search_all_dialogs(client, args.query, args.limit)
        else:
            chat = await client.get_entity(args.chat)
            results = await search_in_chat(client, chat, args.query, args.limit)

        if not results:
            print("Ничего не найдено.")
            return

        print(f"\nВсего найдено треков: {len(results)}\n")
        for message in results:
            print(format_track(message))

        if args.download:
            print("\nНачинаю скачивание...")
            await download_tracks(client, results)


if __name__ == "__main__":
    asyncio.run(main())
