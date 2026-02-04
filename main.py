import os
import telebot
import requests
import random
import numpy as np
import textwrap
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import (
    VideoFileClip, AudioFileClip, ImageClip, CompositeVideoClip,
    concatenate_videoclips
)
import asyncio
import edge_tts  # Yeni TTS paketi

# --- AYARLAR ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

bot = telebot.TeleBot(TELEGRAM_TOKEN)

# YouTube Shorts için NET ve ÇİFT çözünürlük
W, H = 1080, 1920
FPS = 30

# --- FONT ---
def get_font():
    font_path = "Oswald-Bold.ttf"
    if not os.path.exists(font_path):
        url = "https://github.com/google/fonts/raw/main/ofl/oswald/Oswald-Bold.ttf"
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            with open(font_path, "wb") as f:
                f.write(r.content)
    return font_path

# --- TTS (edge-tts async) ---
async def generate_tts(text, out="voice.mp3", voice="en-US-GuyNeural"):
    communicate = edge_tts.Communicate(text, voice)
    try:
        await communicate.save(out)
    except Exception as e:
        print("TTS Hatası:", e)
        # fallback: boş mp3
        with open(out, "wb") as f:
            f.write(b"")

# --- SENARYO ---
def get_script(topic):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    prompt = (
        f"Write a viral scary story about '{topic}'. "
        "110 to 130 words. Short sentences. Strong hook at the start. Simple English."
    )
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        r = requests.post(url, json=payload, timeout=20)
        if r.status_code == 200:
            return r.json()['candidates'][0]['content']['parts'][0]['text'].strip()
    except:
        pass

    return "I looked at my phone. It showed my face. But I was not holding it."

# --- VIDEO BUL ---
def get_videos(total_duration):
    headers = {"Authorization": PEXELS_API_KEY}
    queries = ["dark hallway", "creepy room", "abandoned house", "night corridor", "horror atmosphere"]
    random.shuffle(queries)

    paths = []
    current = 0
    i = 0

    for q in queries:
        if current >= total_duration:
            break

        url = f"https://api.pexels.com/videos/search?query={q}&per_page=5&orientation=portrait"
        r = requests.get(url, headers=headers, timeout=15)
        data = r.json().get("videos", [])

        for v in data:
            if current >= total_duration:
                break

            link = max(v["video_files"], key=lambda x: x["height"])["link"]
            path = f"clip_{i}.mp4"
            i += 1

            with open(path, "wb") as f:
                f.write(requests.get(link, timeout=20).content)

            try:
                clip = VideoFileClip(path)
                current += clip.duration
                clip.close()
                paths.append(path)
            except:
                continue

    return paths

# --- ALTYAZI ---
def make_subtitles(text, duration):
    font_path = get_font()
    font = ImageFont.truetype(font_path, 70)

    words = text.split()
    chunks = []
    temp = []
    for w in words:
        temp.append(w)
        if len(temp) >= 3:
            chunks.append(" ".join(temp))
            temp = []
    if temp:
        chunks.append(" ".join(temp))

    per = duration / max(1, len(chunks))
    clips = []

    for ch in chunks:
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        wrapped = "\n".join(textwrap.wrap(ch.upper(), 12))
        bbox = draw.textbbox((0, 0), wrapped, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]

        x = (W - tw) // 2
        y = int(H * 0.72)

        draw.rectangle([x-30, y-20, x+tw+30, y+th+20], fill=(0,0,0,180))
        draw.text((x, y), wrapped, font=font, fill="white")

        clips.append(ImageClip(np.array(img)).set_duration(per))

    return concatenate_videoclips(clips, method="compose")

# --- CLIP DÜZELT ---
def prepare_clip(path):
    try:
        c = VideoFileClip(path)
        c = c.resize(height=H, resample="lanczos")
        if c.w < W:
            c = c.resize(width=W, resample="lanczos")
        c = c.crop(x_center=c.w/2, y_center=c.h/2, width=W, height=H)
        new_w = int(c.w) // 2 * 2
        new_h = int(c.h) // 2 * 2
        c = c.resize((new_w, new_h))
        return c
    except:
        return None

# --- MONTAJ ---
def build_video(script):
    # --- Async TTS Çağrısı ---
    asyncio.run(generate_tts(script, "voice.mp3"))
    audio = AudioFileClip("voice.mp3")

    paths = get_videos(audio.duration)
    if not paths:
        return None

    clips = []
    for p in paths:
        c = prepare_clip(p)
        if c:
            clips.append(c)

    if not clips:
        return None

    main = concatenate_videoclips(clips, method="compose")

    if main.duration < audio.duration:
        main = main.loop(duration=audio.duration)
    else:
        main = main.subclip(0, audio.duration)

    main = main.set_audio(audio)

    subs = make_subtitles(script, main.duration)
    final = CompositeVideoClip([main, subs], size=(W, H))

    out = "final_video.mp4"
    final.write_videofile(
        out,
        codec="libx264",
        audio_codec="aac",
        fps=FPS,
        threads=2,
        preset="medium"
    )

    # Temizlik
    for c in clips:
        c.close()
    audio.close()
    main.close()
    final.close()

    return out

# --- TELEGRAM ---
@bot.message_handler(commands=["video"])
def handle_video(message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(message, "Bir konu yaz: /video horror story")
        return

    topic = args[1]
    bot.reply_to(message, "🎬 Video hazırlanıyor, lütfen bekle...")

    script = get_script(topic)
    path = build_video(script)

    if path and os.path.exists(path):
        with open(path, "rb") as v:
            bot.send_video(message.chat.id, v, caption=f"🎥 Konu: {topic}")
    else:
        bot.reply_to(message, "❌ Video oluşturulamadı.")

print("Bot çalışıyor...")
bot.polling(non_stop=True)
