"""
Telegram-бот для поиска музыки по названию трека.

Логика:
  Пользователь пишет боту название песни/исполнителя ->
  бот ищет её на YouTube (через yt-dlp) ->
  скачивает лучшую аудиодорожку, конвертирует в mp3 ->
  отправляет пользователю как аудиофайл.

Установка зависимостей:
    pip install pyTelegramBotAPI yt-dlp

Также нужен ffmpeg (для конвертации в mp3):
  - Windows: скачать с https://www.gyan.dev/ffmpeg/builds/ и добавить bin/ в PATH
  - Проверить: в терминале выполнить `ffmpeg -version`

Токен бота (получен у @BotFather в Telegram) НЕ вписывайте прямо в код,
если планируете кому-то показывать этот файл. Задайте его как переменную
окружения:

  Windows (PowerShell):
      $env:BOT_TOKEN = "ваш_токен"
  Windows (cmd):
      set BOT_TOKEN=ваш_токен
  Linux/macOS:
      export BOT_TOKEN=ваш_токен

Запуск:
    python search_music_bot.py
"""

import os
import glob
import shutil
import logging
from typing import Optional

import telebot
import yt_dlp

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("music_bot")

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
DOWNLOAD_DIR = "downloads"
MAX_DURATION_SEC = 15 * 60  # не скачиваем треки длиннее 15 минут (защита от случайных фильмов/подкастов)

if not BOT_TOKEN:
    raise SystemExit(
        "Не задан BOT_TOKEN. Установите переменную окружения BOT_TOKEN "
        "или впишите токен прямо в переменную BOT_TOKEN в коде (не рекомендуется, если делитесь файлом)."
    )

bot = telebot.TeleBot(BOT_TOKEN)
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


def search_and_download(query: str, dest_dir: str) -> Optional[dict]:
    """
    Ищет трек на YouTube по запросу и скачивает лучшую аудиодорожку в mp3.
    Возвращает словарь с метаданными (title, artist, filepath) или None, если ничего не нашлось.
    """
    ydl_opts = {
        "format": "bestaudio/best",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "default_search": "ytsearch1",
        "outtmpl": os.path.join(dest_dir, "%(id)s.%(ext)s"),
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(query, download=False)

        # extract_info с default_search вернёт плейлист из 1 результата
        if "entries" in info:
            entries = [e for e in info["entries"] if e]
            if not entries:
                return None
            info = entries[0]

        duration = info.get("duration") or 0
        if duration and duration > MAX_DURATION_SEC:
            return {"too_long": True, "title": info.get("title"), "duration": duration}

        ydl.download([info["webpage_url"]])
        video_id = info["id"]

    # находим итоговый mp3-файл (после постпроцессинга расширение меняется на .mp3)
    matches = glob.glob(os.path.join(dest_dir, f"{video_id}.mp3"))
    if not matches:
        return None

    return {
        "filepath": matches[0],
        "title": info.get("title") or query,
        "artist": info.get("uploader") or "",
        "duration": info.get("duration") or 0,
        "too_long": False,
    }


@bot.message_handler(commands=["start", "help"])
def handle_start(message):
    bot.reply_to(
        message,
        "Привет! Отправь мне название трека или исполнителя — найду и пришлю аудио.\n"
        "Пример: Виктор Цой - Кукушка",
    )


@bot.message_handler(func=lambda m: True, content_types=["text"])
def handle_search(message):
    query = message.text.strip()
    if not query:
        return

    status = bot.reply_to(message, f"Ищу «{query}»...")

    try:
        result = search_and_download(query, DOWNLOAD_DIR)
    except Exception as e:
        log.exception("Ошибка при поиске/скачивании")
        bot.edit_message_text("Произошла ошибка при поиске. Попробуй другой запрос.",
                               message.chat.id, status.message_id)
        return

    if result is None:
        bot.edit_message_text("Ничего не нашлось. Попробуй сформулировать запрос иначе.",
                               message.chat.id, status.message_id)
        return

    if result.get("too_long"):
        mins = result["duration"] // 60
        bot.edit_message_text(
            f"Нашёл «{result['title']}», но это {mins} мин. — слишком длинное, пропускаю.",
            message.chat.id, status.message_id,
        )
        return

    bot.edit_message_text(f"Нашёл: {result['title']}. Отправляю...", message.chat.id, status.message_id)

    try:
        with open(result["filepath"], "rb") as audio_file:
            bot.send_audio(
                message.chat.id,
                audio_file,
                title=result["title"],
                performer=result["artist"],
            )
    finally:
        # чистим за собой, чтобы диск не забивался
        try:
            os.remove(result["filepath"])
        except OSError:
            pass


if __name__ == "__main__":
    log.info("Бот запущен, жду сообщений...")
    bot.infinity_polling()
