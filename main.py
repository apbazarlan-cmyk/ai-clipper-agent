import os
import subprocess
import yt_dlp
import glob
import requests
import re
import traceback

try:
    print("AI Clipper Agent: Запуск защищенного пайплайна...")

    groq_key = os.environ.get("GROQ_API_KEY")
    if not groq_key:
        print("Ошибка: GROQ_API_KEY не найден в Secrets!")
        exit(1)

    TEST_URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
    output_clip = "vertical_clip.mp4"
    input_video = "test_video.mp4"

    ydl_opts = {
        'format': 'bestvideo[height<=720]+bestaudio/best[height<=720]',
        'outtmpl': input_video,
        'merge_output_format': 'mp4',
        'writesubtitles': True,
        'writeautomaticsub': True,
        'subtitleslangs': ['ru', 'en'],
        'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
    }

    print("Попытка скачивания видео...")
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([TEST_URL])
    except Exception as e:
        print(f"YouTube заблокировал облачный IP: {e}")
        print("Включаем резервный источник для бесперебойного теста...")
        fallback_url = "https://www.w3schools.com/html/mov_bbb.mp4"
        r = requests.get(fallback_url, stream=True)
        with open(input_video, 'wb') as f:
            for chunk in r.iter_content(chunk_size=1024):
                if chunk:
                    f.write(chunk)

    video_files = glob.glob("test_video*")
    if not video_files:
        raise Exception("Видеофайл не найден!")
    input_video = video_files[0]
    print(f"Используем видеофайл: {input_video}")

    subtitle_files = glob.glob("*.vtt") + glob.glob("*.srt")
    transcript_text = "Это тестовый стрим по игре, где происходит самый яркий и динамичный момент."
    if subtitle_files:
        try:
            with open(subtitle_files[0], "r", encoding="utf-8") as f:
                transcript_text = f.read()[:10000]
            print(f"Субтитры успешно прочитаны")
        except Exception as e:
            print(f"Не удалось прочитать субтитры: {e}")

    start_sec = 1
    end_sec = 10

    headers = {
        "Authorization": f"Bearer {groq_key}",
        "Content-Type": "application/json"
    }

    prompt = (
        "Проанализируй текст и найди яркий момент (до 10 секунд). "
        "Напиши таймкоды строго в формате: START: [секунды], END: [секунды]. "
        "Пример: START: 1, END: 10\n\nТекст:\n" + transcript_text
    )

    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": "Ты эксперт по таймкодам. Отвечай строго в формате START: X, END: Y."},
            {"role": "user", "content": prompt}
        ]
    }

    print("Запрос к Groq AI...")
    try:
        response = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=30)
        res_json = response.json()
        if response.status_code == 200 and "choices" in res_json:
            ai_answer = res_json["choices"][0]["message"]["content"]
            print(f"Ответ ИИ:\n{ai_answer}")
            match_start = re.search(r"START:\s*(\d+)", ai_answer)
            match_end = re.search(r"END:\s*(\d+)", ai_answer)
            if match_start and match_end:
                start_sec = int(match_start.group(1))
                end_sec = int(match_end.group(1))
    except Exception as e:
        print(f"Ошибка Groq API, используем стандартные таймкоды: {e}")

    duration = end_sec - start_sec
    if duration <= 0:
        duration = 5

    print(f"Нарезка через FFmpeg: с {start_sec}с, длительность {duration}с...")
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
        print(f"Успех! Вертикальный клип готов. Размер: {size_mb:.2f} MB")
    else:
        print(f"Ошибка FFmpeg:\n{result.stderr}")
        exit(1)

except Exception as e:
    print("Критическая ошибка скрипта:")
    traceback.print_exc()
    exit(1)
