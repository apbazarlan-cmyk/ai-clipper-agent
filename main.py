import os
import subprocess
import yt_dlp
import requests

print("AI Clipper Agent запущен!")

# 1. Проверяем и тестируем Groq API
groq_key = os.environ.get("GROQ_API_KEY")
if groq_key:
    print("Groq API ключ успешно обнаружен!")
    
    print("Делаем тестовый запрос к Groq AI (Llama)...")
    headers = {
        "Authorization": f"Bearer {groq_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": "Привет! Ответь одной короткой фразой: AI Clipper Agent готов к работе?"}]
    }
    
    try:
        response = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload)
        if response.status_code == 200:
            ai_answer = response.json()["choices"][0]["message"]["content"]
            print(f"Ответ от ИИ: {ai_answer}")
        else:
            print(f"Ошибка ответа Groq API: {response.text}")
    except Exception as e:
        print(f"Ошибка при запросе к Groq: {e}")
else:
    print("Внимание: Groq API ключ не найден в Secrets!")

# 2. Скачивание тестового видео
TEST_URL = "https://www.youtube.com/watch?v=BaW_jenozKc"
input_video = "test_video.mp4"
output_clip = "vertical_clip.mp4"

ydl_opts = {
    'format': 'bestvideo[height<=720]+bestaudio/best[height<=720]',
    'outtmpl': input_video,
    'merge_output_format': 'mp4',
}

print("Начинаем скачивание видео...")
try:
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([TEST_URL])
    print("Видео успешно скачано!")
except Exception as e:
    print(f"Ошибка при скачивании: {e}")

# 3. Обрезаем видео в вертикальный формат 9:16 (1080x1920)
print("Запускаем конвертацию в формат 9:16 через FFmpeg...")
try:
    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-i", input_video,
        "-vf", "crop=ih*9/16:ih:(iw-ih*9/16)/2:0,scale=1080:1920",
        "-c:a", "copy",
        output_clip
    ]
    
    result = subprocess.run(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    
    if result.returncode == 0 and os.path.exists(output_clip):
        clip_size = os.path.getsize(output_clip) / (1024 * 1024)
        print(f"Готово! Вертикальный клип 9:16 создан. Размер: {clip_size:.2f} MB")
    else:
        print(f"Ошибка FFmpeg: {result.stderr}")

except Exception as e:
    print(f"Ошибка при запуске FFmpeg: {e}")
