import os
import telebot
import requests
import random
import subprocess
import numpy as np
import textwrap
import time
from gtts import gTTS
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import (
    VideoFileClip, AudioFileClip, ImageClip, CompositeVideoClip,
    concatenate_videoclips
)

# --- AYARLAR ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

bot = telebot.TeleBot(TELEGRAM_TOKEN)

if not hasattr(Image, 'ANTIALIAS'):
    Image.ANTIALIAS = getattr(Image, 'Resampling', Image).LANCZOS

# --- FONT ---
def get_safe_font():
    font_path = "Oswald-Bold.ttf"
    if not os.path.exists(font_path):
        try:
            url = "https://github.com/google/fonts/raw/main/ofl/oswald/Oswald-Bold.ttf"
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                with open(font_path, "wb") as f:
                    f.write(r.content)
        except:
            pass
    return font_path

# --- TTS (EDGE-TTS + YEDEK gTTS) ---
def generate_tts(text, output="voice.mp3"):
    # 1) Önce edge-tts dene
    try:
        cmd = [
            "edge-tts",
            "--voice", "en-US-ChristopherNeural",
            "--text", text,
            "--write-media", output
        ]
        subprocess.run(cmd, check=True)
        print("✅ edge-tts ile ses üretildi")
        return True
    except Exception as e:
        print("⚠️ edge-tts başarısız, gTTS deneniyor:", e)

    # 2) Yedek: gTTS
    try:
        tts = gTTS(text=text, lang="en")
        tts.save(output)
        print("✅ gTTS ile ses üretildi")
        return True
    except Exception as e:
        print("❌ gTTS de başarısız:", e)
        return False

# --- SENARYO ---
def get_script(topic):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    prompt = (
        f"Write a viral and terrifying horror story about '{topic}'. "
        "Use short, punchy sentences. Add suspense every 2-3 sentences. "
        "Start with a shocking hook. Length 110-130 words. No intro or outro. Simple English."
    )
    try:
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        r = requests.post(url, json=payload, timeout=20)
        if r.status_code == 200:
            return r.json()['candidates'][0]['content']['parts'][0]['text'].strip()
    except:
        pass

    return "I looked into the mirror and saw someone else. It was smiling. I was not."

# --- PEXELS VIDEO ---
def get_multiple_videos(total_duration):
    headers = {"Authorization": PEXELS_API_KEY}
    queries = [
        "dark hallway",
        "creepy room",
        "abandoned house",
        "night corridor",
        "horror atmosphere",
        "empty hospital corridor"
    ]

    paths = []
    current_dur = 0
    i = 0
    random.shuffle(queries)

    for q in queries:
        if current_dur >= total_duration:
            break

        try:
            search_url = f"https://api.pexels.com/videos/search?query={q}&per_page=5&orientation=portrait"
            r = requests.get(search_url, headers=headers, timeout=15)
            videos_data = r.json().get("videos", [])
            if not videos_data:
                continue

            v = random.choice(videos_data)
            link = max(v["video_files"], key=lambda x: x["height"])["link"]
            path = f"part_{i}.mp4"
            i += 1

            with open(path, "wb") as f:
                f.write(requests.get(link, timeout=20).content)

            clip = VideoFileClip(path)
            paths.append(path)
            current_dur += clip.duration
            clip.close()
        except:
            continue

    return paths if paths else None

# --- ALTYAZI ---
def split_for_subtitles(text):
    words = text.split()
    chunks = []
    current = []
    for w in words:
        current.append(w)
        if len(current) >= 3:
            chunks.append(" ".join(current))
            current = []
    if current:
        chunks.append(" ".join(current))
    return chunks

def create_subtitles(text, total_duration, video_size):
    W, H = video_size
    font_path = get_safe_font()
    fontsize = int(W / 10)

    try:
        font = ImageFont.truetype(font_path, fontsize)
    except:
        font = ImageFont.load_default()

    chunks = split_for_subtitles(text)
    duration_per_chunk = total_duration / len(chunks)

    clips = []

    for chunk in chunks:
        img = Image.new('RGBA', (int(W), int(H)), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        wrapper = textwrap.TextWrapper(width=15)
        caption_wrapped = '\n'.join(wrapper.wrap(text=chunk.upper()))

        bbox = draw.textbbox((0, 0), caption_wrapped, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]

        draw.rectangle(
            [(W - tw) / 2 - 20, H * 0.7 - 10, (W + tw) / 2 + 20, H * 0.7 + th + 10],
            fill=(0, 0, 0, 180)
        )

        draw.text(
            ((W - tw) / 2, H * 0.7),
            caption_wrapped,
            font=font,
            fill="white",
            align="center"
        )

        clips.append(ImageClip(np.array(img)).set_duration(duration_per_chunk))

    return concatenate_videoclips(clips)

# --- MONTAJ ---
def build_video(script):
    if not generate_tts(script, "voice.mp3"):
        return "TTS üretilemedi."

    audio = AudioFileClip("voice.mp3")

    paths = get_multiple_videos(audio.duration)
    if not paths:
        return "Görüntü bulunamadı."

    video_clips = []
    for p in paths:
        c = VideoFileClip(p).resize(height=1080)
        target_w = int(1080 * 9 / 16)
        if c.w > target_w:
            c = c.crop(x1=(c.w - target_w) / 2, width=target_w, height=1080)
        video_clips.append(c)

    main_video = concatenate_videoclips(video_clips, method="compose")

    if main_video.duration < audio.duration:
        main_video = main_video.loop(duration=audio.duration)
    else:
        main_video = main_video.subclip(0, audio.duration)

    main_video = main_video.set_audio(audio)

    subs = create_subtitles(script, main_video.duration, main_video.size)
    final_result = CompositeVideoClip([main_video, subs])

    out = "final_video.mp4"
    final_result.write_videofile(
        out,
        codec="libx264",
        audio_codec="aac",
        fps=24,
        preset="ultrafast",
        ffmpeg_params=["-pix_fmt", "yuv420p"],
        threads=4
    )

    return out

# --- TELEGRAM ---
@bot.message_handler(commands=['video'])
def handle_video(message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(message, "Lütfen bir konu yaz. Örnek: /video haunted house")
        return

    topic = args[1]
    bot.reply_to(message, f"🎥 '{topic}' için video hazırlanıyor...")

    script = get_script(topic)
    video_path = build_video(script)

    if video_path == "final_video.mp4" and os.path.exists(video_path):
        with open(video_path, 'rb') as v:
            bot.send_video(message.chat.id, v, caption=f"🎬 Konu: {topic}")
    else:
        bot.reply_to(message, f"❌ Hata: {video_path}")

print("Bot çalışıyor...")
bot.polling(non_stop=True)
