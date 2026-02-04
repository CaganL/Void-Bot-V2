import os
import telebot
import requests
import random
import numpy as np
import textwrap
from PIL import Image, ImageDraw, ImageFont
from gtts import gTTS
from moviepy.editor import (
    VideoFileClip, AudioFileClip, ImageClip,
    CompositeVideoClip, concatenate_videoclips
)

# --- AYARLAR ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

bot = telebot.TeleBot(TELEGRAM_TOKEN)

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
    return font_path if os.path.exists(font_path) else None

# --- TTS (gTTS - STABİL) ---
def generate_tts(text, output="voice.mp3"):
    try:
        tts = gTTS(text=text, lang="en", slow=False)
        tts.save(output)
        return True
    except Exception as e:
        print("TTS Hatası:", e)
        return False

# --- SENARYO ---
def get_script(topic):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    prompt = (
        f"Write a viral and terrifying horror story about '{topic}'. "
        "Use short, punchy sentences. Add suspense every 2-3 sentences. "
        "Start with a shocking hook. Length 120-140 words. Simple English."
    )
    try:
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        r = requests.post(url, json=payload, timeout=20)
        if r.status_code == 200:
            return r.json()['candidates'][0]['content']['parts'][0]['text'].strip()
    except:
        pass

    return "I heard my name whispered from the dark hallway. When I opened the door, the house was empty. But the whisper came closer."

# --- PEXELS ---
def get_multiple_videos(min_duration):
    headers = {"Authorization": PEXELS_API_KEY}
    queries = [
        "dark hallway", "creepy room", "abandoned house",
        "night corridor", "horror atmosphere", "empty hospital corridor"
    ]

    paths = []
    total = 0
    i = 0
    random.shuffle(queries)

    for q in queries:
        if total >= min_duration:
            break

        search_url = f"https://api.pexels.com/videos/search?query={q}&per_page=10&orientation=portrait"
        r = requests.get(search_url, headers=headers, timeout=15)
        videos = r.json().get("videos", [])
        if not videos:
            continue

        v = random.choice(videos)
        link = max(v["video_files"], key=lambda x: x["height"])["link"]
        path = f"part_{i}.mp4"
        i += 1

        with open(path, "wb") as f:
            f.write(requests.get(link, timeout=20).content)

        clip = VideoFileClip(path)
        total += clip.duration
        clip.close()
        paths.append(path)

    return paths if paths else None

# --- ALTYAZI ---
def split_for_subtitles(text):
    words = text.split()
    chunks, current = [], []
    for w in words:
        current.append(w)
        if len(current) >= 4:
            chunks.append(" ".join(current))
            current = []
    if current:
        chunks.append(" ".join(current))
    return chunks

def create_subtitles(text, total_duration, video_size):
    W, H = video_size
    font_path = get_safe_font()
    fontsize = int(W / 12)

    try:
        font = ImageFont.truetype(font_path, fontsize)
    except:
        font = ImageFont.load_default()

    chunks = split_for_subtitles(text)
    duration_per = total_duration / len(chunks)
    clips = []

    for chunk in chunks:
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        wrapper = textwrap.TextWrapper(width=18)
        wrapped = "\n".join(wrapper.wrap(chunk.upper()))

        bbox = draw.textbbox((0, 0), wrapped, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]

        draw.text(
            ((W - tw) / 2, H * 0.72),
            wrapped,
            font=font,
            fill="white",
            align="center",
            stroke_width=4,
            stroke_fill="black"
        )

        clips.append(ImageClip(np.array(img)).set_duration(duration_per))

    return concatenate_videoclips(clips)

# --- VIDEO OLUŞTURMA ---
def build_video(script):
    if not generate_tts(script, "voice.mp3"):
        return "TTS üretilemedi."

    audio = AudioFileClip("voice.mp3")

    paths = get_multiple_videos(max(40, audio.duration))
    if not paths:
        return "Video klipleri alınamadı."

    clips = []
    for p in paths:
        c = VideoFileClip(p)

        # 1080x1920 (Shorts formatı) ve ÇİFT SAYI garantisi
        target_h = 1080
        target_w = 608  # çift sayı

        c = c.resize(height=target_h)
        if c.w > target_w:
            x1 = (c.w - target_w) / 2
            c = c.crop(x1=x1, width=target_w, height=target_h)

        clips.append(c)

    main_video = concatenate_videoclips(clips, method="compose")

    if main_video.duration < audio.duration:
        main_video = main_video.loop(duration=audio.duration)
    else:
        main_video = main_video.subclip(0, audio.duration)

    main_video = main_video.set_audio(audio)

    subs = create_subtitles(script, main_video.duration, main_video.size)
    final = CompositeVideoClip([main_video, subs])

    out = "final_video.mp4"
    final.write_videofile(
        out,
        codec="libx264",
        audio_codec="aac",
        fps=24,
        preset="ultrafast",
        ffmpeg_params=["-pix_fmt", "yuv420p"]
    )

    audio.close()
    for c in clips:
        c.close()

    return out

# --- TELEGRAM ---
@bot.message_handler(commands=["video"])
def handle_video(message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(message, "Bir konu yaz. Örnek: /video haunted school")
        return

    topic = args[1]
    bot.reply_to(message, f"🎬 '{topic}' için video hazırlanıyor...")

    script = get_script(topic)
    result = build_video(script)

    if result == "final_video.mp4" and os.path.exists(result):
        with open(result, "rb") as v:
            bot.send_video(message.chat.id, v, caption=f"👻 Topic: {topic}")
    else:
        bot.reply_to(message, result)

print("Bot çalışıyor...")
bot.polling(non_stop=True)
