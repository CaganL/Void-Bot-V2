import os
import telebot
import requests
import random
import subprocess
import time
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import VideoFileClip, AudioFileClip, ImageClip, CompositeVideoClip, concatenate_videoclips

# --- AYARLAR ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

bot = telebot.TeleBot(TELEGRAM_TOKEN)

if not hasattr(Image, "ANTIALIAS"):
    Image.ANTIALIAS = Image.LANCZOS

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
    subprocess.run([
        "edge-tts",
        "--voice", "en-US-ChristopherNeural",
        "--rate", "-10%",
        "--text", text,
        "--write-media", output
    ], check=True)

# --- SENARYO ---
def get_script(topic):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    prompt = (
        f"Write a short, viral documentary style script about {topic}. "
        "Use simple English. About 90-110 words. Start strong. No intro, no outro."
    )

    try:
        r = requests.post(url, json={"contents":[{"parts":[{"text":prompt}]}]}, timeout=20)
        if r.status_code == 200:
            return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    except:
        pass

    return "This place was never on the map. People who went there never came back. The walls were cold. The air was silent. And something was watching."

# --- VİDEO BUL ---
def get_videos(total_duration):
    headers = {"Authorization": PEXELS_API_KEY}
    queries = ["dark corridor", "abandoned building", "creepy room", "night hallway", "empty hospital"]
    paths = []
    current = 0
    i = 0

    random.shuffle(queries)

    for q in queries:
        if current >= total_duration:
            break
        try:
            r = requests.get(f"https://api.pexels.com/videos/search?query={q}&per_page=5&orientation=portrait", headers=headers, timeout=15)
            videos = r.json().get("videos", [])
            if not videos:
                continue

            v = random.choice(videos)
            link = max(v["video_files"], key=lambda x: x["height"])["link"]

            path = f"clip_{i}.mp4"
            i += 1

            with open(path, "wb") as f:
                f.write(requests.get(link, timeout=20).content)

            clip = VideoFileClip(path)
            paths.append(path)
            current += clip.duration
            clip.close()
        except:
            continue

    return paths

# --- ALTYAZI ---
def create_subs(text, duration, size):
    W, H = size
    font_path = get_font()
    try:
        font = ImageFont.truetype(font_path, int(W/12))
    except:
        font = ImageFont.load_default()

    words = text.split()
    chunks = [" ".join(words[i:i+3]) for i in range(0, len(words), 3)]
    dur = duration / len(chunks)

    clips = []

    for c in chunks:
        img = Image.new("RGBA", (W, H), (0,0,0,0))
        draw = ImageDraw.Draw(img)

        bbox = draw.textbbox((0,0), c.upper(), font=font)
        tw = bbox[2]-bbox[0]
        th = bbox[3]-bbox[1]

        x = (W - tw) // 2
        y = int(H * 0.75)

        draw.text((x,y), c.upper(), font=font, fill="white", stroke_width=4, stroke_fill="black")

        clips.append(ImageClip(np.array(img)).set_duration(dur))

    return concatenate_videoclips(clips)

# --- MONTAJ ---
def build_video(topic):
    generate_tts(topic, "voice.mp3")
    audio = AudioFileClip("voice.mp3")

    paths = get_videos(audio.duration)
    if not paths:
        return None

    clips = []
    for p in paths:
        c = VideoFileClip(p).resize(height=1080)
        target_w = int(1080 * 9 / 16)
        if c.w > target_w:
            c = c.crop(x1=(c.w - target_w)//2, width=target_w, height=1080)
        clips.append(c)

    video = concatenate_videoclips(clips, method="compose").subclip(0, audio.duration)
    video = video.set_audio(audio)

    subs = create_subs(topic, video.duration, video.size)
    final = CompositeVideoClip([video, subs])

    out = "final_video.mp4"
    final.write_videofile(out, codec="libx264", audio_codec="aac", fps=24, preset="ultrafast")

    return out

# --- TELEGRAM ---
@bot.message_handler(commands=["video"])
def handle(message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(message, "Kullanım: /video konu")
        return

    topic = args[1]
    msg = bot.reply_to(message, "🎬 Video hazırlanıyor, lütfen bekle...")

    script = get_script(topic)
    path = build_video(script)

    if path:
        with open(path, "rb") as v:
            bot.send_video(message.chat.id, v)
    else:
        bot.reply_to(message, "❌ Video üretilemedi.")

    bot.delete_message(message.chat.id, msg.message_id)

print("Bot çalışıyor...")
bot.polling(non_stop=True)
