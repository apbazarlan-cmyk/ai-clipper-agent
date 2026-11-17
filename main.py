import os
import subprocess
import glob
import requests
import re
import traceback

try:
    print("AI Clipper Agent: Запуск надежного пайплайна...")

    groq_key = os.environ.get("GROQ_API_KEY")
    if not groq_key:
        print("Ошибка: GROQ_API_KEY не найден в Secrets!")
        exit(1)

    output_clip = "vertical_clip.mp4"
    input_video = "test_video.mp4"

    # Используем прямую стабильную ссылку для скачивания без блокировок YouTube
    fallback_url = "https://www.learningcontainer.com/wp-content/uploads/2020/05/sample-mp4-file.mp4"
    
    print("Скачивание тестового видео...")
    try:
        r = requests.get(fallback_url, stream=True, timeout=30, headers={'User-Agent': 'Mozilla/5.0'})
        r.raise_for_status()
        with open(input_video, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        print("Видео успешно скачано.")
    except requests.exceptions.RequestException as req_err:
        print(f"Ошибка HTTP при скачивании видео: {req_err}")
        exit(1)

    if not os.path.exists(input_video) or os.path.getsize(input_video) == 0:
        raise Exception("Видеофайл пустой или не скачался!")

    print(f"Используем видеофайл: {input_video}")

    # Имитируем текст субтитров для теста ИИ
    transcript_text = "Это тестовый игровой стрим, где происходит самый яркий, динамичный и крутой момент."

    start_sec = 1
    end_sec = 8

    headers = {
        "Authorization": f"Bearer {groq_key}",
        "Content-Type": "application/json"
    }

    prompt = (
        "Проанализируй текст и найди яркий момент (до 8 секунд). "
        "Напиши таймкоды строго в формате: START: [секунды], END: [секунды]. "
        "Пример: START: 1, END: 8\n\nТекст:\n" + transcript_text
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
        response.raise_for_status()
        res_json = response.json()
        if "choices" in res_json:
            ai_answer = res_json["choices"][0]["message"]["content"]
            print(f"Ответ ИИ:\n{ai_answer}")
            match_start = re.search(r"START:\s*(\d+)", ai_answer)
            match_end = re.search(r"END:\s*(\d+)", ai_answer)
            if match_start and match_end:
                start_sec = int(match_start.group(1))
                end_sec = int(match_end.group(1))
    except Exception as e:
        print(f"Ошибка Groq API, используем стандартные таймкоды: {e}")

    def get_video_duration(filename):
        try:
            cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", filename]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
            if res.returncode == 0 and res.stdout.strip():
                return float(res.stdout.strip())
        except Exception as ex:
            print(f"Не удалось определить длительность через ffprobe: {ex}")
        return None

    actual_duration = get_video_duration(input_video)
    if actual_duration is not None:
        print(f"Реальная длительность видео: {actual_duration:.2f} сек.")
        if start_sec >= actual_duration:
            start_sec = 0
        if end_sec > actual_duration:
            end_sec = int(actual_duration)
        if start_sec >= end_sec:
            start_sec = max(0, end_sec - 5)

    duration = end_sec - start_sec
    if duration <= 0:
        duration = 5

    print(f"Нарезка через FFmpeg: с {start_sec}с, длительность {duration}с (-t)...")
    
    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-ss", str(start_sec),
        "-i", input_video,
        "-t", str(duration),
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
