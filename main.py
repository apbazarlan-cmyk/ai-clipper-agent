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

    TARGET_CHANNEL_URL = "https://www.youtube.com/@JukinMedia/videos"
    output_clip = "vertical_clip.mp4"
    input_video = "test_video.mp4"

    print(f"Ищем свежее видео на канале: {TARGET_CHANNEL_URL}")
    
    ydl_search_opts = {
        'extract_flat': True,
        'playlist_end': 1,
        'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
    }

    latest_url = None
    try:
        with yt_dlp.YoutubeDL(ydl_search_opts) as ydl:
            info = ydl.extract_info(TARGET_CHANNEL_URL, download=False)
            if 'entries' in info and len(info['entries']) > 0:
                entry = info['entries'][0]
                # Корректное получение полноценного URL видео
                latest_url = entry.get('webpage_url')
                if not latest_url:
                    vid_id = entry.get('id')
                    if vid_id:
                        latest_url = f"https://www.youtube.com/watch?v={vid_id}"
                    else:
                        latest_url = entry.get('url')
    except Exception as e:
        print(f"Не удалось автоматически найти видео через плейлист: {e}")

    if not latest_url or not str(latest_url).startswith('http'):
        latest_url = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
        print(f"Используем запасную ссылку: {latest_url}")
    else:
        print(f"Найдено свежее видео для обработки: {latest_url}")

    ydl_download_opts = {
        'format': 'bestvideo[height<=720]+bestaudio/best[height<=720]',
        'outtmpl': input_video,
        'merge_output_format': 'mp4',
        'writesubtitles': True,
        'writeautomaticsub': True,
        'subtitleslangs': ['ru', 'en'],
        'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
    }

    print("Скачивание видео и субтитров...")
    try:
        with yt_dlp.YoutubeDL(ydl_download_opts) as ydl:
            ydl.download([latest_url])
    except Exception as e:
        print(f"Ошибка скачивания найденного видео, пробуем резервный файл: {e}")
        fallback_url = "https://www.w3schools.com/html/mov_bbb.mp4"
        try:
            r = requests.get(fallback_url, stream=True, timeout=30)
            r.raise_for_status()
            with open(input_video, 'wb') as f:
                for chunk in r.iter_content(chunk_size=1024):
                    if chunk:
                        f.write(chunk)
        except requests.exceptions.RequestException as req_err:
            print(f"Ошибка HTTP при скачивании резервного файла: {req_err}")
            exit(1)

    # Поиск видеофайла с исключением субтитров и служебных файлов
    all_files = glob.glob("test_video*")
    video_files = [f for f in all_files if not f.endswith(('.vtt', '.srt', '.part', '.ytdl', '.json'))]
    if not video_files:
        raise Exception("Видеофайл не найден!")
    input_video = video_files[0]
    print(f"Используем видеофайл: {input_video}")

    # Проверка наличия субтитров без подстановки выдуманного текста
    subtitle_files = glob.glob("*.vtt") + glob.glob("*.srt")
    transcript_text = ""
    if subtitle_files:
        try:
            with open(subtitle_files[0], "r", encoding="utf-8") as f:
                transcript_text = f.read()[:10000]
            print(f"Субтитры успешно прочитаны из {subtitle_files[0]}")
        except Exception as e:
            print(f"Ошибка чтения субтитров: {e}")
    else:
        print("Субтитры не найдены.")

    start_sec = 1
    end_sec = 10

    # Запрос к Groq AI только при наличии реального текста субтитров
    if transcript_text:
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
        except requests.exceptions.RequestException as req_err:
            print(f"Ошибка HTTP при обращении к Groq API, используем стандартные таймкоды: {req_err}")
        except Exception as e:
            print(f"Ошибка обработки ответа Groq AI: {e}")
    else:
        print("Пропускаем анализ Groq AI, так как субтитры отсутствуют. Используем стандартные таймкоды.")

    # Проверка таймкодов по реальной длительности видео через ffprobe
    def get_video_duration(filename):
        try:
            cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", filename]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
            if res.returncode == 0 and res.stdout.strip():
                return float(res.stdout.strip())
        except Exception as ex:
            print(f"Не удалось определить длительность видео через ffprobe: {ex}")
        return None

    actual_duration = get_video_duration(input_video)
    if actual_duration is not None:
        print(f"Реальная длительность видео: {actual_duration:.2f} сек.")
        if start_sec >= actual_navigation := actual_duration:
            start_sec = 0
        if end_sec > actual_duration:
            end_sec = int(actual_duration)
        if start_sec >= end_sec:
            start_sec = max(0, end_sec - 10)

    duration = end_sec - start_sec
    if duration <= 0:
        duration = 5

    print(f"Нарезка через FFmpeg: с {start_sec}с, длительность {duration}с (-t)...")
    
    # Использование параметра -t вместо -to для точной длительности клипа
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
