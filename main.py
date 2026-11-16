import os
import subprocess
import yt_dlp
import glob
import requests
import re
import traceback

try:
    print("AI Clipper Agent: Запуск безопасного пайплайна...")

    groq_key = os.environ.get("GROQ_API_KEY")
    if not groq_key:
        print("Ошибка: GROQ_API_KEY не найден в Secrets!")
        exit(1)

    # Используем стабильное рабочее видео
    TEST_URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
    output_clip = "vertical_clip.mp4"

    ydl_opts = {
        'format': 'bestvideo[height<=720]+bestaudio/best[height<=720]',
        'outtmpl': 'test_video.mp4',
        'merge_output_format': 'mp4',
        'writesubtitles': True,
        'writeautomaticsub': True,
        'subtitleslangs': ['ru', 'en'],
    }

    print("Скачивание видео и субтитров...")
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([TEST_URL])

    video_files = glob.glob("test_video.*")
    if not video_files:
        raise Exception("Видеофайл не найден после скачивания!")
    input_video = video_files[0]
    print(f"Используем видеофайл: {input_video}")

    subtitle_files = glob.glob("*.vtt") + glob.glob("*.srt")
    transcript_text = "Тестовое игровое видео стримера."
    if subtitle_files:
        try:
            with open(subtitle_files[0], "r", encoding="utf-8") as f:
                transcript_text = f.read()[:10000]
            print(f"Субтитры успешно прочитаны из {subtitle_files[0]}")
        except Exception as e:
            print(f"Не удалось прочитать субтитры: {e}")

    start_sec = 1
    end_sec = 15

    headers = {
        "Authorization": f"Bearer {groq_key}",
        "Content-Type": "application/json"
    }

    prompt = (
        "Проанализируй текст субтитров и найди яркий момент (до 15 секунд). "
        "Напиши таймкоды строго в формате: START: [секунды], END: [секунды]. "
        "Пример: START: 1, END: 15\n\nТекст:\n" + transcript_text
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
                print(f"Распознаны таймкоды от ИИ: с {start_sec}с по {end_sec}с")
        else:
            print(f"Предупреждение: Groq ответил с ошибкой: {res_json}. Используем дефолтные таймкоды.")
    except Exception as e:
        print(f"Ошибка при запросе к Groq API: {e}")

    duration = end_sec - start_sec
    if duration <= 0:
        duration = 10

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
