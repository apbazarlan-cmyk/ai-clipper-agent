import glob
import json
import os
import re
import subprocess
import traceback
import requests
import yt_dlp

PROCESSED_FILE = "processed_ids.json"
GROQ_TRANSCRIPTIONS_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
WHISPER_MODEL = "whisper-large-v3-turbo"
LLM_MODEL = "llama-3.3-70b-versatile"
MAX_GROQ_AUDIO_BYTES = 25 * 1024 * 1024
MAX_CLIP_DURATION_SEC = 8.0


def load_processed_ids() -> set[str]:
  if not os.path.exists(PROCESSED_FILE):
    return set()
  try:
    with open(PROCESSED_FILE, "r", encoding="utf-8") as f:
      data = json.load(f)
      if isinstance(data, list):
        return set(data)
      return set(data.get("ids", []))
  except Exception as e:
    print(f"Предупреждение при чтении {PROCESSED_FILE}: {e}")
    return set()


def save_processed_ids(ids: set[str]) -> None:
  with open(PROCESSED_FILE, "w", encoding="utf-8") as f:
    json.dump({"ids": sorted(ids)}, f, ensure_ascii=False, indent=2)


def parse_ts_to_seconds(ts_str: str) -> float | None:
  """Переводит таймкод формата HH:MM:SS.mmm или MM:SS.mmm в секунды."""
  normalized = ts_str.strip().replace(",", ".")
  parts = normalized.split(":")
  try:
    if len(parts) == 3:
      hours = int(parts[0])
      minutes = int(parts[1])
      seconds = float(parts[2])
      return hours * 3600 + minutes * 60 + seconds
    if len(parts) == 2:
      minutes = int(parts[0])
      seconds = float(parts[1])
      return minutes * 60 + seconds
  except ValueError:
    return None
  return None


def clean_cue_text(raw_line: str) -> str:
  """Очищает строку субтитров от тегов разметки, сохраняя сам текст."""
  text = re.sub(r"<[^>]+>", "", raw_line)
  text = re.sub(r"&nbsp;", " ", text)
  text = re.sub(r"&amp;", "&", text)
  text = re.sub(r"&lt;", "<", text)
  text = re.sub(r"&gt;", ">", text)
  text = re.sub(r"\s+", " ", text).strip()
  return text


def parse_subtitle_segments(raw_text: str) -> list[dict]:
  """Парсит VTT/SRT в список сегментов с сохранением временных меток."""
  lines = raw_text.splitlines()
  segments: list[dict] = []

  ts_line_re = re.compile(
      r"^\s*(\d{1,2}:\d{2}:\d{2}[.,]\d{3}|\d{1,2}:\d{2}[.,]\d{3})\s*-->\s*"
      r"(\d{1,2}:\d{2}:\d{2}[.,]\d{3}|\d{1,2}:\d{2}[.,]\d{3})"
  )
  index_re = re.compile(r"^\s*\d+\s*$")

  i = 0
  n = len(lines)
  while i < n:
    line = lines[i].strip()
    if (
        not line
        or line.startswith("WEBVTT")
        or line.startswith("Kind:")
        or line.startswith("Language:")
        or line.startswith("NOTE")
        or index_re.match(line)
    ):
      i += 1
      continue

    m = ts_line_re.match(line)
    if m:
      start_sec = parse_ts_to_seconds(m.group(1))
      end_sec = parse_ts_to_seconds(m.group(2))
      i += 1
      cue_parts = []
      while i < n and lines[i].strip() != "":
        cur = lines[i].strip()
        if not ts_line_re.match(cur) and not index_re.match(cur):
          cleaned = clean_cue_text(cur)
          if cleaned and (not cue_parts or cue_parts[-1] != cleaned):
            cue_parts.append(cleaned)
        i += 1

      full_cue = " ".join(cue_parts).strip()
      if (
          start_sec is not None
          and end_sec is not None
          and end_sec >= start_sec
          and full_cue
      ):
        if not segments or segments[-1]["text"] != full_cue:
          segments.append({
              "start": round(start_sec, 2),
              "end": round(end_sec, 2),
              "text": full_cue,
          })
    else:
      i += 1

  return segments


def format_timestamped_lines(segments: list[dict]) -> str:
  """Формирует структурированный текст реплик с временными метками."""
  formatted = []
  for seg in segments:
    s = float(seg.get("start", 0.0))
    e = float(seg.get("end", s))
    txt = str(seg.get("text", "")).strip()
    if txt:
      formatted.append(f"[{s:.1f}s - {e:.1f}s]: {txt}")
  return "\n".join(formatted)


def extract_subtitles_segments(base_prefix: str = "test_video") -> list[dict]:
  """Ищет субтитры (.vtt / .srt) на en или ru и возвращает сегменты с таймкодами."""
  sub_files = []
  for ext in ("*.vtt", "*.srt"):
    sub_files.extend(glob.glob(f"{base_prefix}*{ext}"))

  if not sub_files:
    return []

  def priority(path: str) -> int:
    name = os.path.basename(path).lower()
    if ".en." in name or "_en." in name:
      return 0
    if ".ru." in name or "_ru." in name:
      return 1
    return 2

  sub_files.sort(key=priority)

  for path in sub_files:
    try:
      with open(path, "r", encoding="utf-8", errors="ignore") as f:
        raw = f.read()
      segs = parse_subtitle_segments(raw)
      if segs:
        print(
            f"Субтитры с таймкодами прочитаны из {path} (реплик: {len(segs)})"
        )
        return segs
    except Exception as e:
      print(f"Не удалось прочитать файл субтитров {path}: {e}")

  return []


def extract_mono_audio(
    video_path: str, audio_output_path: str = "extracted_audio.mp3"
) -> str | None:
  """Извлекает сжатое моно-аудио через FFmpeg для передачи в Whisper."""
  cmd = [
      "ffmpeg",
      "-y",
      "-i",
      video_path,
      "-vn",
      "-ac",
      "1",
      "-ar",
      "16000",
      "-b:a",
      "48k",
      audio_output_path,
  ]
  try:
    res = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=120,
    )
    if (
        res.returncode == 0
        and os.path.exists(audio_output_path)
        and os.path.getsize(audio_output_path) > 0
    ):
      size_bytes = os.path.getsize(audio_output_path)
      print(
          f"Аудио извлечено: {audio_output_path} ({size_bytes / (1024 * 1024):.2f} MB)"
      )
      return audio_output_path
    print(f"FFmpeg не смог извлечь аудио: {res.stderr}")
  except Exception as e:
    print(f"Ошибка при извлечении аудио через FFmpeg: {e}")
  return None


def transcribe_audio_with_groq(
    video_path: str, groq_key: str
) -> list[dict]:
  """Извлекает аудио через FFmpeg и транскрибирует через Groq Whisper."""
  audio_path = extract_mono_audio(video_path, "extracted_audio.mp3")
  if not audio_path:
    return []

  file_size = os.path.getsize(audio_path)
  if file_size > MAX_GROQ_AUDIO_BYTES:
    print(
        f"Размер аудио ({file_size / (1024 * 1024):.2f} MB) превышает лимит"
        " 25 MB для бесплатного тарифа Groq Whisper."
    )
    return []

  print(f"Отправка аудио в Groq Whisper ({WHISPER_MODEL})...")
  try:
    with open(audio_path, "rb") as audio_file:
      resp = requests.post(
          GROQ_TRANSCRIPTIONS_URL,
          headers={"Authorization": f"Bearer {groq_key}"},
          files={"file": (os.path.basename(audio_path), audio_file, "audio/mpeg")},
          data={
              "model": WHISPER_MODEL,
              "response_format": "verbose_json",
              "timestamp_granularities[]": "segment",
          },
          timeout=180,
      )
    resp.raise_for_status()
    data = resp.json()
    raw_segments = data.get("segments") or []
    result_segments: list[dict] = []
    for seg in raw_segments:
      txt = clean_cue_text(str(seg.get("text", "")))
      if not txt:
        continue
      s_val = float(seg.get("start", 0.0))
      e_val = float(seg.get("end", s_val))
      result_segments.append({
          "start": round(max(0.0, s_val), 2),
          "end": round(max(0.0, e_val), 2),
          "text": txt,
      })

    if not result_segments and data.get("text"):
      fallback_txt = clean_cue_text(str(data["text"]))
      if fallback_txt:
        result_segments.append({"start": 0.0, "end": 8.0, "text": fallback_txt})

    print(
        "Транскрибация через Whisper завершена. Сегментов с таймкодами:"
        f" {len(result_segments)}"
    )
    return result_segments
  except Exception as e:
    print(f"Ошибка при транскрибации аудио через Groq Whisper: {e}")
    return []


def get_video_duration_sec(video_path: str) -> float:
  """Возвращает реальную длительность видео в секундах через ffprobe."""
  try:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        video_path,
    ]
    res = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=20,
    )
    if res.returncode == 0 and res.stdout.strip():
      dur = float(res.stdout.strip())
      if dur > 0:
        return dur
  except Exception as e:
    print(f"Не удалось определить длительность через ffprobe: {e}")

  return 10.0


def clamp_clip_window(
    start_sec: float, end_sec: float, total_duration: float
) -> tuple[float, float]:
  """Проверяет и нормализует START и END по длительности видео и лимиту <= 8 сек."""
  safe_total = max(0.5, float(total_duration))
  max_len = min(MAX_CLIP_DURATION_SEC, safe_total)

  s = float(start_sec)
  e = float(end_sec)

  if s < 0.0:
    s = 0.0
  if s >= safe_total:
    s = max(0.0, safe_total - min(1.0, max_len))

  if e <= s:
    e = min(safe_total, s + max_len)

  if e > safe_total:
    e = safe_total

  if e - s > MAX_CLIP_DURATION_SEC:
    e = min(safe_total, s + MAX_CLIP_DURATION_SEC)

  if e <= s:
    s = 0.0
    e = min(safe_total, max_len)

  return round(s, 2), round(e, 2)


try:
  print("AI Clipper Agent: Запуск автопоиска по списку стримеров...")

  groq_key = os.environ.get("GROQ_API_KEY")
  if not groq_key:
    print("Ошибка: GROQ_API_KEY не найден в Secrets!")
    exit(1)

  output_clip = "vertical_clip.mp4"
  input_video = "test_video.mp4"

  # Шаг 1: Читаем список каналов из файла streamers.txt
  channels = []
  if os.path.exists("streamers.txt"):
    with open("streamers.txt", "r", encoding="utf-8") as f:
      channels = [
          line.strip()
          for line in f
          if line.strip() and not line.startswith("#")
      ]

  if not channels:
    channels = ["https://www.youtube.com/@JukinMedia/videos"]
    print("Файл streamers.txt пуст или не найден, используем канал по умолчанию.")

  processed_ids = load_processed_ids()
  latest_url = None
  latest_id = None

  ydl_search_opts = {
      "extract_flat": True,
      "playlist_end": 5,
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
        entries = info.get("entries") if isinstance(info, dict) else None
        if entries:
          for entry in entries:
            if not entry:
              continue
            vid_id = entry.get("id")
            vid_url = entry.get("webpage_url")
            if not vid_url and vid_id:
              vid_url = f"https://www.youtube.com/watch?v={vid_id}"
            dedup_key = vid_id or vid_url
            if dedup_key and dedup_key in processed_ids:
              print(f"Пропускаем уже обработанное видео: {dedup_key}")
              continue
            if vid_url:
              latest_url = vid_url
              latest_id = dedup_key
              print(f"Найдено свежее видео: {latest_url}")
              break
      if latest_url:
        break
    except Exception as e:
      print(f"Не удалось получить видео с канала {ch_url}: {e}")

  use_local_fallback = False
  real_video_downloaded = False

  if not latest_url or not str(latest_url).startswith("http"):
    print(
        "Новое видео не найдено, переключаемся на внутреннюю генерацию для"
        " теста..."
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
        "outtmpl": "test_video.%(ext)s",
        "merge_output_format": "mp4",
        "writesubtitles": True,
        "writeautomaticsubtitles": True,
        "subtitleslangs": ["en", "ru"],
        "subtitlesformat": "vtt/srt/best",
        "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
    }
    print("Скачивание найденного видео и субтитров (en/ru)...")
    try:
      with yt_dlp.YoutubeDL(ydl_download_opts) as ydl:
        ydl.download([latest_url])
      real_video_downloaded = True
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

  # Ищем итоговый видеофайл
  all_files = glob.glob("test_video*")
  video_files = [
      f
      for f in all_files
      if not f.endswith((".vtt", ".srt", ".part", ".ytdl", ".json", ".txt"))
  ]
  if not video_files:
    raise Exception("Видеофайл не найден!")
  input_video = video_files[0]
  print(f"Используем видеофайл: {input_video}")

  # Получаем реальную длительность видео
  total_duration = get_video_duration_sec(input_video)
  print(f"Реальная длительность видео: {total_duration:.2f} сек.")

  # Получаем сегменты с таймкодами: сначала субтитры, при их отсутствии — Whisper
  segments: list[dict] = []
  if real_video_downloaded:
    segments = extract_subtitles_segments("test_video")
    if not segments:
      print(
          "Субтитры (en/ru, обычные и авто) не найдены. Запускаем"
          " транскрибацию аудио через Whisper..."
      )
      segments = transcribe_audio_with_groq(input_video, groq_key)

  timestamped_text = format_timestamped_lines(segments)
  selection_source = "fallback_no_transcript"
  raw_start = 0.0
  raw_end = min(MAX_CLIP_DURATION_SEC, total_duration)

  if timestamped_text:
    headers = {
        "Authorization": f"Bearer {groq_key}",
        "Content-Type": "application/json",
    }
    trimmed_transcript = timestamped_text[:12000]
    prompt = (
        "Ниже приведены реплики с их реальными временными метками в секундах."
        " Выбери один самый яркий или интересный момент длительностью не"
        f" более {MAX_CLIP_DURATION_SEC:.0f} секунд строго в пределах"
        f" длительности видео (0.0 - {total_duration:.1f} сек). Опирайся на"
        " временные метки реплик. Отвечай строго в формате: START: [секунды],"
        " END: [секунды]. Пример: START: 12.5, END: 20.0\n\nРеплики с"
        " таймкодами:\n"
        + trimmed_transcript
    )
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Ты эксперт по нарезке моментов по таймкодам. Отвечай"
                    " строго в формате START: X, END: Y."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    }

    print(
        "Запрос к Groq AI по размеченным по времени репликам"
        f" (модель {LLM_MODEL})..."
    )
    try:
      response = requests.post(
          GROQ_CHAT_URL,
          headers=headers,
          json=payload,
          timeout=30,
      )
      response.raise_for_status()
      res_json = response.json()
      if "choices" in res_json and res_json["choices"]:
        ai_answer = res_json["choices"][0]["message"]["content"]
        print(f"Ответ ИИ:\n{ai_answer}")
        match_start = re.search(r"START:\s*(\d+(?:\.\d+)?)", ai_answer)
        match_end = re.search(r"END:\s*(\d+(?:\.\d+)?)", ai_answer)
        if match_start and match_end:
          raw_start = float(match_start.group(1))
          raw_end = float(match_end.group(1))
          selection_source = "ai_transcript"
        else:
          print(
              "Не удалось распарсить START/END из ответа ИИ — помечаем как"
              " резервную нарезку."
          )
          selection_source = "fallback_parse_error"
      else:
        print(
            "Пустой ответ от Groq Chat — помечаем как резервную нарезку."
        )
        selection_source = "fallback_empty_ai"
    except Exception as e:
      print(
          f"Ошибка Groq Chat API ({e}) — помечаем как резервную нарезку."
      )
      selection_source = "fallback_ai_error"
  else:
    print(
        "Транскрибация отсутствует или не удалась — ИИ по содержанию не"
        " вызывался, используется РЕЗЕРВНАЯ нарезка (не найденный ИИ момент)."
    )
    selection_source = "fallback_no_transcript"

  start_sec, end_sec = clamp_clip_window(raw_start, raw_end, total_duration)
  duration = round(end_sec - start_sec, 2)

  print(
      f"Режим выбора момента: {selection_source} | Нарезка с {start_sec:.2f}с"
      f" по {end_sec:.2f}с (длительность {duration:.2f}с из"
      f" {total_duration:.2f}с)..."
  )

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
    print(
        f"Успех! Клип готов ({selection_source}). Размер: {size_mb:.2f} MB"
    )

    # Сохраняем ID в processed_ids.json только если обработано реальное видео
    if real_video_downloaded and latest_id:
      processed_ids.add(latest_id)
      save_processed_ids(processed_ids)
      print(f"ID реального видео сохранён в {PROCESSED_FILE}: {latest_id}")
    else:
      print(
          f"{PROCESSED_FILE} не обновлён: использовался резервный/тестовый файл"
          " либо ID отсутствует."
      )
  else:
    print(f"Ошибка FFmpeg:\n{result.stderr}")
    exit(1)

except Exception:
  print("Критическая ошибка скрипта:")
  traceback.print_exc()
  exit(1)
