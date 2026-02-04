import os
import telebot
import requests
import random
import subprocess
import numpy as np
import textwrap
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import (
    VideoFileClip, AudioFileClip, ImageClip,
    CompositeVideoClip, concatenate_videoclips
)
from gtts import gTTS

# --- AYARLAR ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

bot = telebot.TeleBot(TELEGRAM_TOKEN)

TARGET_W = 720
TARGET_H = 1280

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
    return font_path if os.path.exists(font_path) else None

# --- TTS ---
def generate_tts(text, output="voice.mp3"):
    # Önce edge-tts dene
    try:
        cmd = [
            "edge-tts",
            "--voice", "en-US-ChristopherNeural",
            "--rate", "-10%",
            "--pitch", "-2Hz",
            "--text", text,
            "--write-media", output
        ]
        subprocess.run(cmd, check=True)
        return True
    except:
        pass

    # Olmazsa gTTS fallback
    try:
        tts = gTTS(text=text, lang="en")
        tts.save(output)
        return True
    except:
        return False

# --- GEMINI SCRIPT ---
def get_script(topic):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    prompt = (
        f"Write a viral, scary horror story about '{topic}'. "
        "Short sentences. Strong hook. Suspense. 130-160 words. Simple English."
    )
    try:
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        r = requests.post(url, json=payload, timeout=20)
        if r.status_code == 200:
            return r.json()['candidates'][0]['content']['parts'][0]['text'].strip()
    except:
        pass

    return "I heard footsteps behind me. But I was alone. Then I realized… I was not."

# --- PEXELS VIDEO ---
def get_videos(min_duration):
    headers = {"Authorization": PEXELS_API_KEY}
    queries = [
        "dark hallway", "creepy room", "abandoned house",
        "night corridor", "horror atmosphere", "empty hospital"
    ]
    random.shuffle(queries)

    paths = []
    total = 0
    idx = 0

    for q in queries:
        if total >= min_duration:
            break

        url = f"https://api.pexels.com/videos/search?query={q}&per_page=10&orientation=portrait"
        r = requests.get(url, headers=headers, timeout=20)
        vids = r.json().get("videos", [])
        if not vids:
            continue

        v = random.choice(vids)
        link = max(v["video_files"], key=lambda x: x["height"])["link"]

        path = f"part_{idx}.mp4"
        idx += 1

        with open(path, "wb") as f:
            f.write(requests.get(link, timeout=30).content)

        try:
            clip = VideoFileClip(path)
            total += clip.duration
            clip.close()
            paths.append(path)
        except:
            pass

    return paths

# --- SUBTITLES ---
def make_subtitles(text, duration):
    font_path = get_font()
    font_size = 64

    try:
        font = ImageFont.truetype(font_path, font_size)
    except:
        font = ImageFont.load_default()

    words = text.split()
    chunks = [" ".join(words[i:i+4]) for i in range(0, len(words), 4)]
    per = duration / len(chunks)

    clips = []

    for chunk in chunks:
        img = Image.new("RGBA", (TARGET_W, TARGET_H), (0,0,0,0))
        draw = ImageDraw.Draw(img)

        wrapper = textwrap.TextWrapper(width=20)
        txt = "\n".join(wrapper.wrap(chunk.upper()))

        bbox = draw.textbbox((0,0), txt, font=font)
        tw = bbox[2]-bbox[0]
        th = bbox[3]-bbox[1]

        draw.text(
            ((TARGET_W-tw)//2, int(TARGET_H*0.75)),
            txt,
            font=font,
            fill="white",
            stroke_width=3,
            stroke_fill="black",
            align="center"
        )

        clips.append(ImageClip(np.array(img)).set_duration(per))

    return concatenate_videoclips(clips)

# --- BUILD VIDEO ---
def build_video(script):
    if not generate_tts(script, "voice.mp3"):
        return "TTS üretilemedi."

    audio = AudioFileClip("voice.mp3")
    paths = get_videos(audio.duration + 5)

    if not paths:
        return "Video bulunamadı."

    clips = []

    for p in paths:
        try:
            c = VideoFileClip(p)
            c = c.resize(height=TARGET_H)

            if c.w > TARGET_W:
                x1 = (c.w - TARGET_W)//2
                c = c.crop(x1=x1, width=TARGET_W, height=TARGET_H)
            else:
                c = c.resize((TARGET_W, TARGET_H))

            clips.append(c)
        except:
            pass

    if not clips:
        return "Video klipleri işlenemedi."

    main = concatenate_videoclips(clips, method="compose")

    if main.duration < audio.duration:
        main = main.loop(duration=audio.duration)
    else:
        main = main.subclip(0, audio.duration)

    main = main.set_audio(audio)

    subs = make_subtitles(script, main.duration)
    final = CompositeVideoClip([main, subs])

    out = "final_video.mp4"
    final.write_videofile(
        out,
        fps=24,
        codec="libx264",
        audio_codec="aac",
        ffmpeg_params=["-pix_fmt", "yuv420p"]
    )

    return out

# --- TELEGRAM ---
@bot.message_handler(commands=["video"])
def handle_video(message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(message, "Bir konu yaz. Örnek: /video haunted mirror")
        return

    topic = args[1]
    bot.reply_to(message, "🎬 Video hazırlanıyor, biraz bekle...")

    script = get_script(topic)
    result = build_video(script)

    if result == "final_video.mp4" and os.path.exists(result):
        with open(result, "rb") as v:
            bot.send_video(message.chat.id, v, caption=f"👻 {topic}")
    else:
        bot.reply_to(message, result)

print("Bot çalışıyor...")
bot.polling(non_stop=True)
