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
        url = "https://github.com/google/fonts/raw/main/ofl/oswald/Oswald-Bold.ttf"
        try:
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                with open(font_path, "wb") as f:
                    f.write(r.content)
        except:
            pass
    return font_path

# --- TTS ---
def generate_tts(text, output="voice.mp3"):
    try:
        cmd = [
            "edge-tts",
            "--voice", "en-US-ChristopherNeural",
            "--rate", "-5%",
            "--pitch", "-2Hz",
            "--text", text,
            "--write-media", output
        ]
        subprocess.run(cmd, check=True)
        return True
    except Exception as e:
        print("TTS Hatası:", e)
        return False

# --- SENARYO ---
def get_script(topic):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    prompt = (
        f"Write a viral horror story about '{topic}' for YouTube Shorts. "
        "Start with a shocking hook. Use simple English. "
        "Short sentences. Suspense. Length 120-150 words. No intro, no outro."
    )
    try:
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        r = requests.post(url, json=payload, timeout=20)
        if r.status_code == 200:
            return r.json()['candidates'][0]['content']['parts'][0]['text'].strip()
    except:
        pass

    return "I heard footsteps behind me. But I was home alone. The door was locked. Then I felt someone breathing on my neck."

# --- Hook'u başa al ---
def make_hook_script(script):
    sentences = script.replace("!", ".").replace("?", ".").split(".")
    sentences = [s.strip() for s in sentences if s.strip()]
    if len(sentences) < 3:
        return script
    hook = sentences[0]
    rest = ". ".join(sentences[1:])
    return f"{hook}. {rest}."

# --- PEXELS ---
def get_videos(total_duration):
    headers = {"Authorization": PEXELS_API_KEY}
    queries = [
        "dark hallway", "creepy room", "abandoned house",
        "night corridor", "horror atmosphere", "empty hospital"
    ]

    paths = []
    current = 0
    i = 0
    random.shuffle(queries)

    for q in queries:
        if current >= total_duration:
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

            clip = VideoFileClip(path)
            if clip.duration > 4:
                paths.append(path)
                current += clip.duration
            clip.close()
        except:
            continue

    return paths

# --- ALTYAZI ---
def split_subs(text):
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
    return chunks

def create_subtitles(text, total_duration, size):
    W, H = size
    font_path = get_font()
    try:
        font = ImageFont.truetype(font_path, int(W / 12))
    except:
        font = ImageFont.load_default()

    chunks = split_subs(text)
    dur = total_duration / len(chunks)

    clips = []
    for c in chunks:
        img = Image.new("RGBA", (W, H), (0,0,0,0))
        draw = ImageDraw.Draw(img)

        txt = c.upper()
        bbox = draw.textbbox((0,0), txt, font=font)
        tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]

        x = (W - tw) / 2
        y = H * 0.75

        draw.rectangle([x-20, y-10, x+tw+20, y+th+10], fill=(0,0,0,180))
        draw.text((x, y), txt, font=font, fill="white", stroke_width=3, stroke_fill="black")

        clips.append(ImageClip(np.array(img)).set_duration(dur))

    return concatenate_videoclips(clips)

# --- MONTAJ ---
def build_video(script):
    if not generate_tts(script, "voice.mp3"):
        return "TTS üretilemedi."

    audio = AudioFileClip("voice.mp3")

    paths = get_videos(audio.duration + 5)
    if not paths:
        return "Video bulunamadı."

    clips = []
    for p in paths:
        c = VideoFileClip(p).resize(height=1080)
        target_w = int(1080 * 9 / 16)
        if c.w > target_w:
            c = c.crop(x_center=c.w/2, width=target_w, height=1080)
        clips.append(c)

    main = concatenate_videoclips(clips, method="compose")

    if main.duration < audio.duration:
        main = main.loop(duration=audio.duration)
    else:
        main = main.subclip(0, audio.duration)

    main = main.set_audio(audio)

    subs = create_subtitles(script, main.duration, main.size)
    final = CompositeVideoClip([main, subs])

    out = "final_video.mp4"
    final.write_videofile(
        out,
        codec="libx264",
        audio_codec="aac",
        fps=30,
        preset="medium",
        threads=4,
        ffmpeg_params=["-pix_fmt", "yuv420p"]
    )

    return out

# --- TELEGRAM ---
@bot.message_handler(commands=["video"])
def handle_video(message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(message, "Bir konu yaz. Örnek: /video haunted house")
        return

    topic = args[1]
    bot.reply_to(message, f"🎬 '{topic}' için Shorts hazırlanıyor...")

    script = get_script(topic)
    script = make_hook_script(script)

    path = build_video(script)

    if path == "final_video.mp4" and os.path.exists(path):
        with open(path, "rb") as v:
            bot.send_video(message.chat.id, v, caption=f"🎥 Topic: {topic}")
    else:
        bot.reply_to(message, str(path))

print("Bot çalışıyor...")
bot.polling(non_stop=True)
