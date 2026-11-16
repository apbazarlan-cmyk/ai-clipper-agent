
import os
import re
import glob
import html
import subprocess
import requests
import yt_dlp

print("AI Clipper Agent: запуск...")

GROQ_KEY = os.getenv("GROQ_API_KEY")
TEST_URL = "https://www.youtube.com/watch?v=BaW_jenozKc"

VIDEO_PREFIX = "downloaded_video"
OUTPUT_CLIP = "vertical_clip.mp4"


def clean_old_files():
    for path in glob.glob(VIDEO_PREFIX + ".*"):
        try:
            os.remove(path)
        except OSError:
            pass


def timestamp_to_seconds(value):
    parts = value.replace(",", ".").split(":")
    if len(parts) == 3:
        hours, minutes, seconds = parts
    elif len(parts) == 2:
        hours = 0
        minutes, seconds = parts
    else:
        raise ValueError("Неверный формат времени")

    return (
        int(hours) * 3600
        + int(minutes) * 60
        + float(seconds)
    )


def read_subtitles():
    files = glob.glob(VIDEO_PREFIX + "*.vtt")
    if not files:
        files = glob.glob(VIDEO_PREFIX + "*.srt")

    if not files:
        raise RuntimeError("Субтитры не найдены")

    with open(files[0], "r", encoding="utf-8") as f:
        content = f.read()

    pattern = (
        r"((?:\d{2}:)?\d{2}:\d{2}[.,]\d{3})"
        r"\s+-->\s+"
        r"((?:\d{2}:)?\d{2}:\d{2}[.,]\d{3})"
        r"[^\n]*\n(.*?)(?=\n\s*\n|\Z)"
    )

    cues = []

    for match in re.finditer(pattern, content, re.S):
        start = timestamp_to_seconds(match.group(1))
        end = timestamp_to_seconds(match.group(2))

        text = match.group(3)
        text = re.sub(r"<[^>]+>", "", text)
        text = html.unescape(text)
        text = " ".join(text.split())

        if text:
            cues.append(
                f"[{start:.2f}-{end:.2f}] {text}"
            )

    if not cues:
        raise RuntimeError("Не удалось прочитать субтитры")

    return "\n".join(cues)


def get_video_duration(path):
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            path
        ],
        capture_output=True,
        text=True,
        check=True
    )

    return float(result.stdout.strip())


def main():
    if not GROQ_KEY:
        raise RuntimeError("GROQ_API_KEY не найден")

    clean_old_files()

    # 1. Скачивание видео
    print("Скачиваем видео...")

    options = {
        "format": "bestvideo[height<=720]+bestaudio/best[height<=720]/best",
        "outtmpl": VIDEO_PREFIX + ".%(ext)s",
        "merge_output_format": "mp4",
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": ["en", "ru"],
        "subtitlesformat": "vtt/best",
        "noplaylist": True,
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        ydl.download([TEST_URL])

    # 2. Находим настоящий скачанный видеофайл
    excluded = (".vtt", ".srt", ".json", ".part", ".ytdl")

    video_files = [
        f for f in glob.glob(VIDEO_PREFIX + ".*")
        if not f.endswith(excluded)
        and os.path.getsize(f) > 1024
    ]

    if not video_files:
        raise RuntimeError("Видео после скачивания не найдено")

    video_files.sort(
        key=lambda f: f.endswith(".mp4"),
        reverse=True
    )

    input_video = video_files[0]

    print("Видео найдено:", input_video)

    duration = get_video_duration(input_video)
    print(f"Длительность видео: {duration:.2f} сек.")

    # 3. Читаем субтитры с таймкодами
    print("Читаем субтитры...")

    transcript = read_subtitles()[:12000]

    # 4. Анализируем через Groq
    print("Отправляем текст в Groq AI...")

    prompt = f"""
Проанализируй субтитры видео.

Найди один самый интересный момент:
юмор, неожиданное событие, эмоции или интересный диалог.

Выбери фрагмент продолжительностью от 10 до 30 секунд.

Временные метки в квадратных скобках —
это реальные временные отметки субтитров.

Не придумывай таймкоды.

Ответь строго:
START: число
END: число

Длительность видео: {duration:.2f} секунд.

Субтитры:
{transcript}
"""

    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {GROQ_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {
                    "role": "system",
                    "content": "Выбирай только реальные таймкоды из предоставленных субтитров."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.2
        },
        timeout=60
    )

    response.raise_for_status()

    answer = response.json()["choices"][0]["message"]["content"]

    print("Ответ Groq:")
    print(answer)

    start_match = re.search(
        r"START:\s*(\d+(?:\.\d+)?)", answer
    )
    end_match = re.search(
        r"END:\s*(\d+(?:\.\d+)?)", answer
    )

    if not start_match or not end_match:
        raise RuntimeError("Groq вернул неверный формат таймкодов")

    start_sec = float(start_match.group(1))
    end_sec = float(end_match.group(1))

    clip_duration = end_sec - start_sec

    if (
        start_sec < 0
        or end_sec > duration
        or clip_duration < 10
        or clip_duration > 30
    ):
        raise RuntimeError("ИИ выбрал некорректные таймкоды")

    print(f"Выбран момент: {start_sec} - {end_sec}")

    # 5. Создаём вертикальный клип
    print("Запускаем FFmpeg...")

    command = [
        "ffmpeg", "-y",
        "-ss", str(start_sec),
        "-i", input_video,
        "-t", str(clip_duration),
        "-vf",
        "crop=ih*9/16:ih:(iw-ih*9/16)/2:0,scale=1080:1920",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "23",
        "-c:a", "aac",
        "-movflags", "+faststart",
        OUTPUT_CLIP
    ]

    subprocess.run(command, check=True)

    # 6. Проверяем результат
    if not os.path.exists(OUTPUT_CLIP):
        raise RuntimeError("Готовый клип не найден")

    if os.path.getsize(OUTPUT_CLIP) < 1024:
        raise RuntimeError("Готовый клип слишком маленький")

    output_duration = get_video_duration(OUTPUT_CLIP)
    size_mb = os.path.getsize(OUTPUT_CLIP) / (1024 * 1024)

    print("--------------------------------")
    print("УСПЕХ! КЛИП СОЗДАН")
    print(f"Файл: {OUTPUT_CLIP}")
    print(f"Длительность: {output_duration:.2f} сек.")
    print(f"Размер: {size_mb:.2f} MB")
    print("--------------------------------")


if __name__ == "__main__":
    main()
