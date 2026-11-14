import os
import subprocess

print("AI Clipper Agent запущен и готов к работе!")

# 1. Проверяем наличие Groq API ключа
groq_key = os.environ.get("GROQ_API_KEY")
if groq_key:
    print("Groq API ключ успешно обнаружен.")
else:
    print("Внимание: Groq API ключ не найден в переменных окружения!")

# 2. Проверяем доступность FFmpeg
try:
    result = subprocess.run(
        ["ffmpeg", "-version"], 
        stdout=subprocess.PIPE, 
        stderr=subprocess.PIPE, 
        text=True
    )
    if result.returncode == 0:
        print("FFmpeg успешно установлен и готов к нарезке видео!")
    else:
        print("Ошибка: FFmpeg установлен, но вернул ошибку.")
except Exception as e:
    print(f"FFmpeg не найден на сервере: {e}")

# 3. Проверяем работу yt-dlp (импорт библиотеки)
try:
    import yt_dlp
    print("Библиотека yt-dlp успешно загружена. Готовы скачивать видео!")
except ImportError:
    print("Ошибка: yt-dlp не установлена.")
