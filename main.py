import glob
import json
import os
import re
import subprocess
import traceback
import requests
import yt_dlp

PROCESSED_FILE = "processed_ids.json"


def load_processed_ids() -> set[str]:
  if not os.path.exists(PROCESSED_FILE):
    return set()
  try:
    with open(PROCESSED_FILE, "r", encoding="utf-8") as f:
      return set(json.load(f).get("ids", []))
  except Exception:
    return set()


def save_processed_ids(ids: set[str]) -> None:
  with open(PROCESSED_FILE, "w", encoding="utf-8") as f:
    json.dump({"ids": sorted(ids)}, f, ensure_ascii=False, indent=2)


try:
  print("AI Clipper Agent: Запуск автопоиска по списку стримеров...")

  groq_key = os.environ.get("GROQ_API_KEY")
  if not groq_key:
    print("Ошибка: GROQ_API_KEY не найден в Secrets!")
    exit(1)

  output_clip = "vertical_clip.mp4"
  input_video = "test_video.mp4"

  channels = []
  if os.path.exists("streamers.txt"):
    with open("streamers.txt", "r", encoding="utf-8") as f:
      channels = [
          line.strip() for line in f if line.strip() and not line.startswith("#")
      ]

  if not channels:
    channels = ["https://www.youtube.com/@JukinMedia/videos"]
    print("Файл streamers.txt пуст или не найден, используем канал по умолчанию.")

  processed_ids = load_processed_ids()
  latest_url = None
  latest_id = None

  ydl_search_opts = {
      "extract_flat": True,
      "playlist_end": 3,
      "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
  }

  for ch_url in channels:
    target = (
        ch_url if "/videos" in ch_url or "@" in ch_url else ch_url + "/videos"
    )
    print(f"Проверяем канал: {target}")
    try:
      with yt_dlp.YoutubeDL(ydl_search_opts) as ydl:
        info = ydl.extract_info(target, download=False)
        for entry in info.get("entries") or []:
          vid_id = entry.get("id")
          vid_url = entry.get("webpage_url") or (
              f"https://www.youtube.com/watch?v={vid_id}" if vid_id else None
          )
          key = vid_id or vid_url
          if key and key in processed_ids:
            print(f"Пропускаю уже обработанное видео: {key}")
            continue
          if vid_url:
            latest_url = vid_url
            latest_id = key
            print(f"Найдено новое видео: {latest_url}")
            break
      if latest_url:
        break
    except Exception as e:
      print(f"Не удалось получить видео с канала {ch_url}: {e}")

  use_local_fallback = False
  if not latest_url or not str(latest_url).startswith("http"):
    print(
        "Новых видео в автопоиске нет или не вернулись ссылки — включаем"
        " локальный тест..."
    )
    use_local_fallback = True

  if use_local_fallback:
    print("Генерация локального тестового видео через FFmpeg...")
    gen_cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "testsrc=size=1280x720:rate=30:duration=10",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:duration=10",
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
        input_video,
    ]
    subprocess.run(
        gen_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )
  else:
    ydl_download_opts = {
        "format": "bestvideo[height<=720]+bestaudio/best[height<=720]",
        "outtmpl": input_video,
        "merge_output_format": "mp4",
        "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
    }
    print("Скачивание найденного видео...")
    try:
      with yt_dlp.YoutubeDL(ydl_download_opts) as ydl:
        ydl.download([latest_url])
    except Exception as e:
      print(
          f"Ошибка скачивания с YouTube: {e}. Генерируем резервный файл."
      )
      gen_cmd = [
          "ffmpeg",
          "-y",
          "-f",
          "lavfi",
          "-i",
          "testsrc=size=1280x720:rate=30:duration=10",
          "-c:v",
          "libx264",
          input_video,
      ]
      subprocess.run(
          gen_cmd,
          stdout=subprocess.PIPE,
          stderr=subprocess.PIPE,
          text=True,
          check=True,
      )

  all_files = glob.glob("test_video*")
  video_files = [
      f
      for f in all_files
      if not f.endswith((".vtt", ".srt", ".part", ".ytdl", ".json"))
  ]
  if not video_files:
    raise Exception("Видеофайл не найден!")
  input_video = video_files[0]
  print(f"Используем видеофайл: {input_video}")

  transcript_text = (
      "Это тестовый стрим по игре, где происходит самый яркий момент."
  )
  start_sec = 1
  end_sec = 8

  headers = {
      "Authorization": f"Bearer {groq_key}",
      "Content-Type": "application/json",
  }
  prompt = (
      "Проанализируй текст и найди яркий момент (до 8 секунд). "
      "Напиши таймкоды строго в формате: START: [секунды], END: [секунды]. "
      "Пример: START: 1, END: 8\n\nТекст:\n" + transcript_text
  )
  payload = {
      "model": "llama-3.3-70b-versatile",
      "messages": [
          {
              "role": "system",
              "content": (
                  "Ты эксперт по таймкодам. Отвечай строго в формате START: X,"
                  " END: Y."
              ),
          },
          {"role": "user", "content": prompt},
      ],
  }

  print("Запрос к Groq AI...")
  try:
    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers=headers,
        json=payload,
        timeout=30,
    )
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

  duration = end_sec - start_sec
  if duration <= 0 or duration > 9:
    duration = 5

  print(f"Нарезка через FFmpeg: с {start_sec}с, длительность {duration}с...")
  ffmpeg_cmd = [
      "ffmpeg",
      "-y",
      "-ss",
      str(start_sec),
      "-i",
      input_video,
      "-t",
      str(duration),
      "-vf",
      "crop=ih*9/16:ih:(iw-ih*9/16)/2:0,scale=1080:1920",
      "-c:v",
      "libx264",
      "-c:a",
      "aac",
      output_clip,
  ]

  result = subprocess.run(
      ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
  )

  if result.returncode == 0 and os.path.exists(output_clip):
    size_mb = os.path.getsize(output_clip) / (1024 * 1024)
    print(f"Успех! Автоматический клип готов. Размер: {size_mb:.2f} MB")
    if latest_id:
      processed_ids.add(latest_id)
      save_processed_ids(processed_ids)
      print(f"ID сохранён в {PROCESSED_FILE}: {latest_id}")
  else:
    print(f"Ошибка FFmpeg:\n{result.stderr}")
    exit(1)

except Exception as e:
  print("Критическая ошибка скрипта:")
  traceback.print_exc()
  exit(1)
