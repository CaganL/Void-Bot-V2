import os
import telebot
import requests
import random
import subprocess
import numpy as np
import textwrap
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

# --- FONT ---
def get_font():
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

# --- TTS ---
def generate_tts(text, output="voice.mp3"):
    # Edge-TTS dene
    try:
        cmd = [
            "edge-tts",
            "--voice", "en-US-GuyNeural",
            "--text", text,
            "--write-media", output
        ]
        subprocess.run(cmd, check=True)
        if os.path.exists(output) and os.path.getsize(output) > 1000:
            return True
    except:
        pass

    # Yedek: gTTS
    try:
        from gtts import gTTS
        tts = gTTS(text=text, lang="en")
        tts.save(output)
        return True
    except:
        return False

# --- SENARYO ---
def get_script(topic):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    prompt = (
        f"Write a viral and scary story about '{topic}' for YouTube Shorts. "
        "Start with a strong hook. Simple English. 140-160 words. No intro or outro."
    )
    try:
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        r = requests.post(url, json=payload, timeout=20)
        if r.status_code == 200:
            return r.json()['candidates'][0]['content']['parts'][0]['text'].strip()
    except:
        pass

    return "I thought I was alone in the house. Then I heard my own voice calling my name from the dark hallway."

# --- VIDEO BUL ---
def get_videos(target_duration):
    headers = {"Authorization": PEXELS_API_KEY}
    queries = [
        "dark hallway", "creepy room", "abandoned house",
        "night corridor", "horror atmosphere", "empty hospital"
    ]

    paths = []
    total = 0
    i = 0

    random.shuffle(queries)

    for q in queries:
        if total >= target_duration + 5:
            break
        try:
            r = requests.get(
                f"https://api.pexels.com/videos/search?query={q}&per_page=5&orientation=portrait",
                headers=headers, timeout=15
            )
            data = r.json().get("videos", [])
            if not data:
                continue

            v = random.choice(data)
            link = max(v["video_files"], key=lambda x: x["height"])["link"]
            path = f"part_{i}.mp4"
            i += 1

            with open(path, "wb") as f:
                f.write(requests.get(link, timeout=20).content)

            try:
                clip = VideoFileClip(path)
                if clip.duration < 1:
                    clip.close()
                    os.remove(path)
                    continue
                paths.append(path)
                total += clip.duration
                clip.close()
            except:
                if os.path.exists(path):
                    os.remove(path)
                continue

        except:
            pass

    return paths if paths else None

# --- ALTYAZI ---
def make_subtitles(text, duration, size):
    W, H = size
    font_path = get_font()
    try:
        font = ImageFont.truetype(font_path, int(W / 12))
    except:
        font = ImageFont.load_default()

    words = text.split()
    chunks = []
    buf = []
    for w in words:
        buf.append(w)
        if len(buf) >= 3:
            chunks.append(" ".join(buf))
            buf = []
    if buf:
        chunks.append(" ".join(buf))

    per = duration / len(chunks)
    clips = []

    for ch in chunks:
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)

        txt = ch.upper()
        bbox = d.textbbox((0, 0), txt, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]

        x = (W - tw) // 2
        y = int(H * 0.78)

        d.rectangle([x-20, y-10, x+tw+20, y+th+10], fill=(0,0,0,180))
        d.text((x, y), txt, font=font, fill="white")

        clips.append(ImageClip(np.array(img)).set_duration(per))

    return concatenate_videoclips(clips)

# --- MONTAJ ---
def build_video(script):
    if not generate_tts(script, "voice.mp3"):
        return "TTS üretilemedi."

    audio = AudioFileClip("voice.mp3")

    paths = get_videos(max(40, audio.duration))
    if not paths:
        return "Görüntü bulunamadı."

    clips = []

    for p in paths:
        try:
            c = VideoFileClip(p).resize(height=1920)

            target_w = int(1920 * 9 / 16)
            if target_w % 2 != 0:
                target_w += 1

            if c.w > target_w:
                x1 = int((c.w - target_w) / 2)
                c = c.crop(x1=x1, width=target_w, height=1920)

            # Çift sayı garantisi
            if c.w % 2 != 0:
                c = c.resize(width=c.w + 1)
            if c.h % 2 != 0:
                c = c.resize(height=c.h + 1)

            clips.append(c)
        except:
            continue

    if not clips:
        return "Video klipler işlenemedi."

    main = concatenate_videoclips(clips, method="compose")

    if main.duration < audio.duration:
        main = main.loop(duration=audio.duration)
    else:
        main = main.subclip(0, audio.duration)

    main = main.set_audio(audio)

    subs = make_subtitles(script, main.duration, main.size)
    final = CompositeVideoClip([main, subs])

    out = "final_video.mp4"
    final.write_videofile(
        out,
        codec="libx264",
        audio_codec="aac",
        fps=30,
        preset="ultrafast",
        ffmpeg_params=["-pix_fmt", "yuv420p"],
        threads=4
    )

    return out

# --- TELEGRAM ---
@bot.message_handler(commands=["video"])
def handle_video(message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(message, "Bir konu yaz: /video horror story")
        return

    topic = args[1]
    bot.reply_to(message, f"🎬 '{topic}' için video hazırlanıyor...")

    script = get_script(topic)
    video_path = build_video(script)

    if isinstance(video_path, str) and os.path.exists(video_path):
        with open(video_path, "rb") as v:
            bot.send_video(message.chat.id, v, caption=f"🎥 Konu: {topic}")
    else:
        bot.reply_to(message, str(video_path))

print("Bot çalışıyor...")
bot.polling(non_stop=True)
