import os
import telebot
import requests
import subprocess
import numpy as np
import textwrap
import time
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import VideoFileClip, AudioFileClip, ImageClip, CompositeVideoClip, concatenate_videoclips

# --- AYARLAR ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

bot = telebot.TeleBot(TELEGRAM_TOKEN, skip_pending=True)

# Webhook varsa sil (conflict azaltır)
try:
    bot.remove_webhook()
except:
    pass

if not hasattr(Image, 'ANTIALIAS'):
    Image.ANTIALIAS = Image.LANCZOS

# --- FONT ---
def download_font():
    font_path = "Oswald-Bold.ttf"
    if not os.path.exists(font_path):
        url = "https://github.com/google/fonts/raw/main/ofl/oswald/Oswald-Bold.ttf"
        try:
            r = requests.get(url, timeout=10)
            with open(font_path, "wb") as f:
                f.write(r.content)
        except:
            pass
    return font_path

# --- TTS ---
def generate_tts(text, output="voice.mp3"):
    cmd = [
        "edge-tts",
        "--voice", "en-US-ChristopherNeural",
        "--text", text,
        "--write-media", output
    ]
    subprocess.run(cmd, check=True)

# --- SENARYO ---
def get_script(topic):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    prompt = (
        f"Write a scary, viral horror story about '{topic}' for a YouTube Short. "
        "110-120 words. Simple English. Start with a strong hook. No intro or outro."
    )
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    r = requests.post(url, json=payload, timeout=20)
    if r.status_code == 200:
        return r.json()['candidates'][0]['content']['parts'][0]['text'].strip()
    return "I looked into the mirror. Something was looking back. And it was not me."

# --- VIDEO İNDİR ---
def get_videos(query, total_duration):
    headers = {"Authorization": PEXELS_API_KEY}
    search_url = f"https://api.pexels.com/videos/search?query={query}&per_page=8&orientation=portrait"
    r = requests.get(search_url, headers=headers, timeout=15)
    videos = r.json().get("videos", [])
    if not videos:
        return None

    paths = []
    dur = 0
    i = 0

    for v in videos:
        if dur >= total_duration:
            break
        link = max(v["video_files"], key=lambda x: x["height"])["link"]
        path = f"part_{i}.mp4"
        with open(path, "wb") as f:
            f.write(requests.get(link, timeout=20).content)
        clip = VideoFileClip(path)
        paths.append(path)
        dur += clip.duration
        clip.close()
        i += 1

    return paths

# --- ALTYAZI ---
def create_subtitles(text, total_duration, size):
    W, H = size
    font_path = download_font()
    font = ImageFont.truetype(font_path, int(W / 10))

    words = text.split()
    chunks = [" ".join(words[i:i+4]) for i in range(0, len(words), 4)]
    dur = total_duration / len(chunks)

    clips = []
    for chunk in chunks:
        img = Image.new("RGBA", (W, H), (0,0,0,0))
        draw = ImageDraw.Draw(img)

        wrapper = textwrap.TextWrapper(width=18)
        wrapped = "\n".join(wrapper.wrap(chunk.upper()))

        bbox = draw.textbbox((0,0), wrapped, font=font)
        tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]

        draw.text(((W-tw)/2, H*0.75), wrapped, font=font, fill="white", stroke_width=4, stroke_fill="black")

        clips.append(ImageClip(np.array(img)).set_duration(dur))

    return concatenate_videoclips(clips)

# --- MONTAJ ---
def build_video(topic, script):
    generate_tts(script, "voice.mp3")
    audio = AudioFileClip("voice.mp3")

    paths = get_videos(topic, audio.duration)
    if not paths:
        return None

    clips = []
    for p in paths:
        c = VideoFileClip(p).resize(height=1920)
        target_w = int(1920 * 9 / 16)
        if c.w > target_w:
            c = c.crop(x1=(c.w-target_w)//2, width=target_w, height=1920)
        clips.append(c)

    main = concatenate_videoclips(clips).subclip(0, audio.duration)
    main = main.set_audio(audio)

    subs = create_subtitles(script, main.duration, main.size)
    final = CompositeVideoClip([main, subs])

    out = "final_video.mp4"
    final.write_videofile(out, codec="libx264", audio_codec="aac", fps=30, preset="ultrafast")

    return out

# --- TELEGRAM ---
@bot.message_handler(commands=['video'])
def handle_video(message):
    try:
        topic = message.text.split(maxsplit=1)[1]
    except:
        bot.reply_to(message, "Kullanım: /video konu")
        return

    bot.reply_to(message, f"🎬 '{topic}' hazırlanıyor...")

    script = get_script(topic)
    path = build_video(topic, script)

    if path and os.path.exists(path):
        with open(path, "rb") as v:
            bot.send_video(message.chat.id, v)
    else:
        bot.reply_to(message, "❌ Video üretilemedi.")

# --- GÜVENLİ POLLING ---
while True:
    try:
        bot.polling(none_stop=True, interval=0, timeout=60)
    except Exception as e:
        print("Polling error, restarting:", e)
        time.sleep(5)
