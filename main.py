import os
import subprocess
import yt_dlp
import requests

print("AI Clipper Agent запущен и готов к работе!")

# 1. Проверяем ключ Groq API
groq_key = os.environ.get("GROQ_API_KEY")
if not groq_key:
    print("Ошибка: Groq API ключ не найден в Secrets!")
    exit(1)

headers = {
    "Authorization": f"Bearer {groq_key}",
    "Content-Type": "application/json"
}

# 2. Скачивание тестового видео и субтитров через yt-dlp
TEST_URL = "https://www.youtube.com/watch?v=BaW_jenozKc"
input_video = "test_video.mp4"
output_clip = "vertical_clip.mp4"

ydl_opts = {
    'format': 'bestvideo[height<=720]+bestaudio/best[height<=720]',
    'outtmpl': input_video,
    'merge_output_format': 'mp4',
    'writesubtitles': True,          # Скачиваем субтитры, если они есть
    'writeautomaticsub': True,       # Или автосубтитры от YouTube
    'subtitleslangs': ['ru', 'en'],   # Русский или английский язык
}

print("Скачиваем видео и субтитры...")
try:
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([TEST_URL])
    print("Видео и данные успешно загружены!")
except Exception as e:
    print(f"Ошибка при скачивании: {e}")

# 3. Отправляем запрос к Groq AI для поиска динамичных моментов
print("Анализируем видео через Groq AI (Llama)...")
prompt_text = (
    "Ты профессиональный видеомонтажер рилсов и шортсов. "
    "Предложи таймкоды (начало и конец) для самого динамичного и цепляющего момента "
    "продолжительностью до 30 секунд. Выдай ответ в формате: Старт: [сек], Конец: [сек]."
)

payload = {
    "model": "llama-3.3-70b-versatile",
    "messages": [
        {"role": "system", "content": "Ты эксперт по вирусному контенту."},
        {"role": "user", "content": prompt_text}
    ]
}

try:
    response = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload)
    if response.status_code == 200:
        ai_answer = response.json()["choices"][0]["message"]["content"]
        print(f"ИИ определил лучшие моменты:\n{ai_answer}")
    else:
        print(f"Ошибка ответа Groq API: {response.text}")
except Exception as e:
    print(f"Ошибка при запросе к Groq: {e}")

# 4. Обрезаем видео в вертикальный формат 9:16 (1080x1920) через FFmpeg
print("Запускаем конвертацию в формат 9:16...")
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
        print(f"Готово! Вертикальный клип 9:16 успешно создан. Размер: {clip_size:.2f} MB")
    else:
        print(f"Ошибка FFmpeg: {result.stderr}")

except Exception as e:
    print(f"Ошибка при запуске FFmpeg: {e}")
