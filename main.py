import os
import telebot
import requests
import random
import asyncio
import edge_tts
import numpy as np
import textwrap
import time
from PIL import Image, ImageDraw, ImageFont 
from moviepy.editor import VideoFileClip, AudioFileClip, ImageClip, CompositeVideoClip, concatenate_videoclips

# --- AYARLAR ---
TELEGRAM_TOKEN = "8395962603:AAFmuGIsQ2DiUD8nV7ysUjkGbsr1dmGlqKo"
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Müzik Kütüphanesi
MUSIC_LIBRARY = {
    "horror": "https://www.chosic.com/wp-content/uploads/2021/07/The-Dead-Are-Coming.mp3",
    "motivation": "https://www.chosic.com/wp-content/uploads/2021/10/Epic-Adventure.mp3",
    "calm": "https://www.chosic.com/wp-content/uploads/2020/06/Lofi-Study.mp3",
    "info": "https://www.chosic.com/wp-content/uploads/2021/04/Corporate-Uplifting-Motivational.mp3"
}

bot = telebot.TeleBot(TELEGRAM_TOKEN)

# --- 1. GEMINI ZEKA MERKEZİ ---
def get_ai_content(topic):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    # Gemini'den hem hikaye hem de tek kelimelik mood istiyoruz
    prompt = (f"Write a viral story about {topic} in 120 words. "
              "Format: [STORY] your story here [/STORY] [MOOD] horror or motivation or calm or info [/MOOD]")
    
    try:
        response = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=15)
        text = response.json()['candidates'][0]['content']['parts'][0]['text']
        
        story = text.split("[STORY]")[1].split("[/STORY]")[0].strip()
        mood = text.split("[MOOD]")[1].split("[/MOOD]")[0].strip().lower()
        return story, mood
    except:
        return "The system encountered a logic error.", "calm"

# --- 2. DEV ALTYAZI SİSTEMİ ---
def create_subtitles(text, total_duration, video_size):
    W, H = video_size
    font_path = "Oswald-Bold.ttf"
    if not os.path.exists(font_path):
        r = requests.get("https://github.com/google/fonts/raw/main/ofl/oswald/Oswald-Bold.ttf")
        with open(font_path, "wb") as f: f.write(r.content)

    fontsize = int(W / 8.5) 
    font = ImageFont.truetype(font_path, fontsize)
    sentences = text.replace(".", ".|").replace("?", "?|").replace("!", "!|").split("|")
    chunks = [s.strip() for s in sentences if s.strip()]
    duration_per_chunk = total_duration / len(chunks)
    
    clips = []
    for chunk in chunks:
        img = Image.new('RGBA', (int(W), int(H)), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        wrapper = textwrap.TextWrapper(width=14)
        caption_wrapped = '\n'.join(wrapper.wrap(text=chunk))
        bbox = draw.textbbox((0, 0), caption_wrapped, font=font)
        tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
        draw.text(((W-tw)/2, H*0.65), caption_wrapped, font=font, fill="#FFD700", align="center", stroke_width=7, stroke_fill="black")
        clips.append(ImageClip(np.array(img)).set_duration(duration_per_chunk))
    return concatenate_videoclips(clips)

# --- 3. MONTAJ MOTORU ---
def build_video(topic, script, mood):
    try:
        # Seslendirme
        asyncio.run(edge_tts.Communicate(script, "en-US-ChristopherNeural").save("voice.mp3"))
        audio = AudioFileClip("voice.mp3")
        
        # MÜZİK İNDİRME VE KONTROL
        music_url = MUSIC_LIBRARY.get(mood, MUSIC_LIBRARY["calm"])
        r_music = requests.get(music_url, stream=True)
        with open("bg.mp3", "wb") as f:
            for chunk in r_music.iter_content(chunk_size=1024):
                if chunk: f.write(chunk)
        
        # Dosyanın tam indiğinden emin olmak için kısa bir bekleme
        time.sleep(2)
        bg = AudioFileClip("bg.mp3").volumex(0.12).set_duration(audio.duration)
        
        from moviepy.audio.AudioClip import CompositeAudioClip
        final_audio = CompositeAudioClip([audio, bg])
        
        # Pexels Sahneleri
        headers = {"Authorization": PEXELS_API_KEY}
        r = requests.get(f"https://api.pexels.com/videos/search?query={topic}&per_page=5&orientation=portrait", headers=headers)
        videos_data = r.json().get("videos", [])
        
        video_clips = []
        for i, v in enumerate(videos_data[:5]):
            link = max(v["video_files"], key=lambda x: x["height"])["link"]
            path = f"p_{i}.mp4"
            with open(path, "wb") as f: f.write(requests.get(link).content)
            c = VideoFileClip(path)
            nh = 1080
            nw = int((nh * (c.w / c.h)) // 2) * 2
            c = c.resize(height=nh, width=nw).crop(x1=(nw/2 - 304), width=608, height=1080)
            video_clips.append(c)

        main_v = concatenate_videoclips(video_clips, method="compose").loop(duration=audio.duration)
        main_v = main_v.set_audio(final_audio)
        subs = create_subtitles(script, audio.duration, main_v.size)
        final = CompositeVideoClip([main_v, subs])
        
        final.write_videofile("out.mp4", codec="libx264", audio_codec="aac", fps=24, preset='ultrafast', ffmpeg_params=["-pix_fmt", "yuv420p"])
        return "out.mp4"
    except Exception as e: return str(e)

@bot.message_handler(commands=['video'])
def handle(message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(message, "Konu girin.")
        return
    topic = args[1]
    bot.reply_to(message, f"🎭 Gemini '{topic}' analiz ediyor...")
    
    script, mood = get_ai_content(topic)
    bot.send_message(message.chat.id, f"🧠 AI Kararı: {mood.upper()}\n🎬 Montaj başladı...")
    
    res = build_video(topic, script, mood)
    if "out.mp4" in res:
        with open(res, 'rb') as v: bot.send_video(message.chat.id, v, caption=f"✨ Mood: {mood.upper()}")
    else: bot.reply_to(message, f"❌ Hata: {res}")

bot.polling()
