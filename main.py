import os
import subprocess
import yt_dlp

print("AI Clipper Agent запущен!")

# 1. Проверяем ключ Groq
groq_key = os.environ.get("GROQ_API_KEY")
if groq_key:
    print("Groq API ключ обнаружен.")
else:
    print("Ошибка: Groq API ключ не найден!")

# 2. Тестируем скачивание короткого видео через yt-dlp
TEST_URL = "https://www.youtube.com/watch?v=BaW_jenozKc"  # Короткое тестовое видео
output_template = "test_video.mp4"

ydl_opts = {
    'format': 'bestvideo[height<=720]+bestaudio/best[height<=720]',
    'outtmpl': output_template,
    'merge_output_format': 'mp4',
}

print(f"Начинаем скачивание тестового видео...")
try:
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([TEST_URL])
    print("Видео успешно скачано!")
    
    # Проверяем размер файла
    if os.path.exists(output_template):
        file_size = os.path.getsize(output_template) / (1024 * 1024)
        print(f"Размер скачанного файла: {file_size:.2f} MB")
    else:
        print("Ошибка: файл видео не найден после скачивания.")

except Exception as e:
    print(f"Ошибка при скачивании через yt-dlp: {e}")

# 3. Проверяем FFmpeg
try:
    result = subprocess.run(["ffmpeg", "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode == 0:
        print("FFmpeg готов к нарезке вертикальных клипов 9:16!")
    else:
        print("FFmpeg вернул ошибку.")
except Exception as e:
    print(f"FFmpeg не найден: {e}")
