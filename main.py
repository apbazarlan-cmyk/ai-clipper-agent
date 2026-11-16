import os
import subprocess
import yt_dlp
import glob
import requests
import re

print("AI Clipper Agent: Запуск умной нарезки...")

groq_key = os.environ.get("GROQ_API_KEY")
if not groq_key:
    print("Ошибка: Groq API ключ не найден в Secrets!")
    exit(1)

# 1. Скачиваем видео и субтитры
TEST_URL = "https://www.youtube.com/watch?v=BaW_jenozKc"
input_video = "test_video.mp4"
output_clip = "vertical_clip.mp4"

ydl_opts = {
    'format': 'bestvideo[height<=720]+bestaudio/best[height<=720]',
    'outtmpl': input_video,
    'merge_output_format': 'mp4',
    'writesubtitles': True,
    'writeautomaticsub': True,
    'subtitleslangs': ['ru', 'en'],
}

print("Скачивание видео и субтитров...")
with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    ydl.download([TEST_URL])

# 2. Читаем субтитры
subtitle_files = glob.glob("*.vtt") + glob.glob("*.srt")
transcript_text = ""
if subtitle_files:
    try:
        with open(subtitle_files[0], "r", encoding="utf-8") as f:
            transcript_text = f.read()[:12000]
    except Exception as e:
        print(f"Ошибка чтения субтитров: {e}")

if not transcript_text:
    transcript_text = "Тестовое игровое видео стримера."

# 3. Запрос к Groq AI за точными таймкодами
headers = {
    "Authorization": f"Bearer {groq_key}",
    "Content-Type": "application/json"
}

prompt = (
    "Проанализируй текст субтитров и найди самый яркий момент (до 30 секунд). "
    "Обязательно напиши таймкоды в строгом формате: START: [секунды], END: [секунды]. "
    "Например: START: 15, END: 45\n\nТекст:\n" + transcript_text
)

payload = {
    "model": "llama-3.3-70b-versatile",
    "messages": [
        {"role": "system", "content": "Ты эксперт по таймкодам. Отвечай строго в формате START: X, END: Y."},
        {"role": "user", "content": prompt}
    ]
}

print("Анализ текста через Groq AI...")
response = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload)

start_sec = 10  г# Дефолтные значения на случай сбоя
end_sec = 35

if response.status_code == 200:
    ai_answer = response.json()["choices"][0]["message"]["content"]
    print(f"Ответ ИИ:\n{ai_answer}")
    
    # Ищем цифры после START и END
    match_start = re.search(r"START:\s*(\d+)", ai_answer)
    match_end = re.search(r"END:\s*(\d+)", ai_answer)
    
    if match_start and match_end:
        start_sec = int(match_start.group(1))
        end_sec = int(match_end.group(1))
        print(f"Распознанные таймкоды: с {start_sec}с по {end_sec}с")
else:
    print(f"Ошибка Groq API: {response.text}")

# 4. Нарезка точного фрагмента в 9:16 через FFmpeg
print(f"Вырезаем фрагмент с {start_sec} по {end_sec секунду} и конвертируем в 9:16...")
try:
    duration = end_sec - start_sec
    if duration <= 0:
        duration = 20

    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-ss", str(start_sec),
        "-i", input_video,
        "-to", str(duration),
        "-vf", "crop=ih*9/16:ih:(iw-ih*9/16)/2:0,scale=1080:1920",
        "-c:v", "libx264", "-c:a", "aac",
        output_clip
    ]
    
    result = subprocess.run(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    
    if result.returncode == 0 and os.path.exists(output_clip):
        size_mb = os.path.getsize(output_clip) / (1024 * 1024)
        print(f"Успех! Точечный вертикальный клип готов. Размер: {size_mb:.2f} MB")
    else:
        print(f"Ошибка FFmpeg: {result.stderr}")

except Exception as e:
    print(f"Ошибка при нарезке: {e}")
