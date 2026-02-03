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

bot = telebot.TeleBot(TELEGRAM_TOKEN, threaded=False)

# --- GÜVENLİ İNDİRME FONKSİYONU ---
def download_file(url, target_name):
    try:
        with requests.get(url, stream=True, timeout=15) as r:
            r.raise_for_status()
            with open(target_name, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        return True
    except:
        return False

# --- AI SENARYO VE MOOD ANALİZİ ---
def get_ai_data(topic):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    prompt = f"Write a 110 word story about {topic}. At the very end add: MOOD: horror (or motivation, calm, info)"
    try:
        res = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=10).json()
        raw = res['candidates'][0]['content']['parts'][0]['text']
        mood = "calm"
        for m in MUSIC_LIBRARY.keys():
            if m in raw.lower(): mood = m
        return raw.split("MOOD:")[0].strip(), mood
    except:
        return "The shadows whispered in the dark...", "horror"

# --- DEV ALTYAZI ---
def draw_subs(text, duration, size):
    W, H = size
    font_p = "Oswald-Bold.ttf"
    if not os.path.exists(font_p):
        open(font_p, "wb").write(requests.get("https://github.com/google/fonts/raw/main/ofl/oswald/Oswald-Bold.ttf").content)
    
    font = ImageFont.truetype(font_p, int(W / 8.5))
    lines = [s.strip() for s in text.replace(".", ".|").replace("?", "?|").split("|") if s.strip()]
    dur_per = duration / len(lines)
    
    clips = []
    for l in lines:
        img = Image.new('RGBA', (int(W), int(H)), (0, 0, 0, 0))
        wrapped = '\n'.join(textwrap.wrap(l, width=14))
        draw = ImageDraw.Draw(img)
        bbox = draw.textbbox((0, 0), wrapped, font=font)
        tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
        draw.text(((W-tw)/2, H*0.65), wrapped, font=font, fill="#FFD700", stroke_width=7, stroke_fill="black", align="center")
        clips.append(ImageClip(np.array(img)).set_duration(dur_per))
    return concatenate_videoclips(clips)

# --- ANA MOTOR ---
def make_video(topic, script, mood):
    try:
        # 1. Seslendirme
        asyncio.run(edge_tts.Communicate(script, "en-US-ChristopherNeural").save("v.mp3"))
        audio = AudioFileClip("v.mp3")
        
        # 2. Müzik Miksajı (ZIRHLI: İnemezse hata vermez)
        final_audio = audio
        m_url = MUSIC_LIBRARY.get(mood)
        if download_file(m_url, "bg.mp3"):
            try:
                bg = AudioFileClip("bg.mp3").volumex(0.12).set_duration(audio.duration)
                from moviepy.audio.AudioClip import CompositeAudioClip
                final_audio = CompositeAudioClip([audio, bg])
            except: pass # Müzik hatalıysa sessiz devam et
            
        # 3. Görüntüler
        h = {"Authorization": PEXELS_API_KEY}
        r = requests.get(f"https://api.pexels.com/videos/search?query={topic}&per_page=5&orientation=portrait", headers=h).json()
        video_clips = []
        for i, v in enumerate(r.get("videos", [])[:5]):
            v_url = max(v["video_files"], key=lambda x: x["height"])["link"]
            if download_file(v_url, f"p{i}.mp4"):
                c = VideoFileClip(f"p{i}.mp4")
                nh, nw = 1080, int((1080 * (c.w / c.h)) // 2) * 2
                c = c.resize(height=nh, width=nw).crop(x1=(nw/2-304), width=608, height=1080)
                video_clips.append(c)

        main_v = concatenate_videoclips(video_clips, method="compose").loop(duration=audio.duration).set_audio(final_audio)
        subs = draw_subs(script, audio.duration, main_v.size)
        final = CompositeVideoClip([main_v, subs])
        
        final.write_videofile("out.mp4", codec="libx264", audio_codec="aac", fps=24, preset='ultrafast', ffmpeg_params=["-pix_fmt", "yuv420p"])
        return "out.mp4"
    except Exception as e: return f"Hata: {str(e)}"

@bot.message_handler(commands=['video'])
def start(m):
    if len(m.text.split()) < 2: return bot.reply_to(m, "Konu girin.")
    topic = m.text.split(maxsplit=1)[1]
    bot.reply_to(m, f"🎬 '{topic}' kurgusu başladı...")
    
    script, mood = get_ai_data(topic)
    res = make_video(topic, script, mood)
    
    if "out.mp4" in res:
        with open(res, 'rb') as v: bot.send_video(m.chat.id, v, caption=f"✨ Mood: {mood.upper()}")
    else: bot.reply_to(m, res)

# Railway çakışmasını engellemek için botu başlatmadan önce bir saniye bekle
time.sleep(1)
bot.polling(non_stop=True)
