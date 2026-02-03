import os
import telebot
import requests
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

MUSIC_LIBRARY = {
    "horror": "https://www.chosic.com/wp-content/uploads/2021/07/The-Dead-Are-Coming.mp3",
    "motivation": "https://www.chosic.com/wp-content/uploads/2021/10/Epic-Adventure.mp3",
    "calm": "https://www.chosic.com/wp-content/uploads/2020/06/Lofi-Study.mp3",
    "info": "https://www.chosic.com/wp-content/uploads/2021/04/Corporate-Uplifting-Motivational.mp3"
}

bot = telebot.TeleBot(TELEGRAM_TOKEN)

def safe_download(url, filename):
    try:
        r = requests.get(url, stream=True, timeout=20)
        with open(filename, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk: f.write(chunk)
        # Dosya boyutunu kontrol et
        return os.path.exists(filename) and os.path.getsize(filename) > 0
    except: return False

# --- 1. GEMINI ZEKA MERKEZİ ---
def get_ai_content(topic):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    prompt = (f"Write a 110 word viral story about {topic}. "
              "End your response with MOOD: [one of horror, motivation, calm, info]")
    try:
        res = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=15).json()
        full_text = res['candidates'][0]['content']['parts'][0]['text']
        
        mood = "calm"
        for m in MUSIC_LIBRARY.keys():
            if m in full_text.lower(): mood = m
        
        story = full_text.split("MOOD:")[0].replace("*", "").strip()
        return story, mood
    except: return "A story about silence and shadows...", "calm"

# --- 2. DEV ALTYAZI ---
def create_subtitles(text, duration, size):
    W, H = size
    font_path = "Oswald-Bold.ttf"
    if not os.path.exists(font_path):
        r = requests.get("https://github.com/google/fonts/raw/main/ofl/oswald/Oswald-Bold.ttf")
        with open(font_path, "wb") as f: f.write(r.content)

    fontsize = int(W / 8.5)
    font = ImageFont.truetype(font_path, fontsize)
    sentences = [s.strip() for s in text.replace(".", ".|").replace("?", "?|").split("|") if s.strip()]
    dur_per = duration / len(sentences)
    
    clips = []
    for s in sentences:
        img = Image.new('RGBA', (int(W), int(H)), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        wrapped = '\n'.join(textwrap.wrap(s, width=15))
        bbox = draw.textbbox((0, 0), wrapped, font=font)
        tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
        draw.text(((W-tw)/2, H*0.65), wrapped, font=font, fill="#FFD700", align="center", stroke_width=7, stroke_fill="black")
        clips.append(ImageClip(np.array(img)).set_duration(dur_per))
    return concatenate_videoclips(clips)

# --- 3. MONTAJ MOTORU ---
def build_video(topic, script, mood):
    try:
        asyncio.run(edge_tts.Communicate(script, "en-US-ChristopherNeural").save("v.mp3"))
        audio = AudioFileClip("v.mp3")
        
        # MÜZİK İNDİRME GÜVENLİĞİ
        m_url = MUSIC_LIBRARY.get(mood, MUSIC_LIBRARY["calm"])
        if not safe_download(m_url, "bg.mp3"): return "Müzik indirilemedi."
        
        bg = AudioFileClip("bg.mp3").volumex(0.12).set_duration(audio.duration)
        from moviepy.audio.AudioClip import CompositeAudioClip
        final_audio = CompositeAudioClip([audio, bg])
        
        # Pexels
        h = {"Authorization": PEXELS_API_KEY}
        r = requests.get(f"https://api.pexels.com/videos/search?query={topic}&per_page=5&orientation=portrait", headers=h).json()
        
        video_clips = []
        for i, v in enumerate(r.get("videos", [])[:5]):
            link = max(v["video_files"], key=lambda x: x["height"])["link"]
            if safe_download(link, f"p{i}.mp4"):
                c = VideoFileClip(f"p{i}.mp4")
                nh, nw = 1080, int((1080 * (c.w / c.h)) // 2) * 2
                c = c.resize(height=nh, width=nw).crop(x1=(nw/2-304), width=608, height=1080)
                video_clips.append(c)

        main_v = concatenate_videoclips(video_clips, method="compose").loop(duration=audio.duration).set_audio(final_audio)
        subs = create_subtitles(script, audio.duration, main_v.size)
        final = CompositeVideoClip([main_v, subs])
        
        final.write_videofile("out.mp4", codec="libx264", audio_codec="aac", fps=24, preset='ultrafast', ffmpeg_params=["-pix_fmt", "yuv420p"])
        return "out.mp4"
    except Exception as e: return f"Hata: {str(e)}"

@bot.message_handler(commands=['video'])
def handle(message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2: return bot.reply_to(message, "Konu girin.")
    
    bot.reply_to(message, "🧠 AI analiz ediyor...")
    script, mood = get_ai_content(args[1])
    bot.send_message(message.chat.id, f"🎭 Mood: {mood.upper()}\n🎬 Kurgu başlıyor...")
    
    res = build_video(args[1], script, mood)
    if "out.mp4" in res:
        with open(res, 'rb') as v: bot.send_video(message.chat.id, v, caption=f"✨ {mood.upper()}")
    else: bot.reply_to(message, res)

bot.polling()
