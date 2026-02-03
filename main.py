import os
import telebot
import requests
import random
import asyncio
import edge_tts
import numpy as np
import textwrap
from PIL import Image, ImageDraw, ImageFont 
from moviepy.editor import VideoFileClip, AudioFileClip, ImageClip, CompositeVideoClip, concatenate_videoclips

# --- AYARLAR VE MÜZİK KÜTÜPHANESİ ---
TELEGRAM_TOKEN = "8395962603:AAFmuGIsQ2DiUD8nV7ysUjkGbsr1dmGlqKo"
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# İnternet üzerindeki telifsiz müzik linkleri
MUSIC_LIBRARY = {
    "horror": "https://www.chosic.com/wp-content/uploads/2021/07/The-Dead-Are-Coming.mp3",
    "motivation": "https://www.chosic.com/wp-content/uploads/2021/10/Epic-Adventure.mp3",
    "calm": "https://www.chosic.com/wp-content/uploads/2020/06/Lofi-Study.mp3"
}

bot = telebot.TeleBot(TELEGRAM_TOKEN)

# --- 1. MOOD ANALİZİ (RUH HALİ ÖLÇER) ---
def detect_mood(script):
    script_lower = script.lower()
    # Korku kelimeleri
    if any(word in script_lower for word in ["scary", "horror", "ghost", "dark", "mirror", "creepy", "blood", "death"]):
        return "horror"
    # Motivasyon kelimeleri
    if any(word in script_lower for word in ["success", "dream", "hustle", "achieve", "motivation", "power", "money"]):
        return "motivation"
    # Varsayılan
    return "calm"

# --- 2. DEV ALTYAZI SİSTEMİ ---
def create_subtitles(text, total_duration, video_size):
    W, H = video_size
    font_path = "Oswald-Bold.ttf"
    if not os.path.exists(font_path):
        url = "https://github.com/google/fonts/raw/main/ofl/oswald/Oswald-Bold.ttf"
        r = requests.get(url)
        with open(font_path, "wb") as f: f.write(r.content)

    fontsize = int(W / 8.5) # Dev boyut
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
        
        # SARI YAZI + KALIN SİYAH ÇERÇEVE
        draw.text(((W-tw)/2, H*0.65), caption_wrapped, font=font, fill="#FFD700", align="center", stroke_width=7, stroke_fill="black")
        clips.append(ImageClip(np.array(img)).set_duration(duration_per_chunk))
    return concatenate_videoclips(clips)

# --- 3. MONTAJ MOTORU ---
def build_video(topic, script):
    try:
        # Seslendirme
        asyncio.run(edge_tts.Communicate(script, "en-US-ChristopherNeural").save("voice.mp3"))
        audio = AudioFileClip("voice.mp3")
        
        # RUH HALİNE GÖRE MÜZİK ÇEKME
        mood = detect_mood(script)
        music_url = MUSIC_LIBRARY.get(mood)
        
        r_music = requests.get(music_url)
        with open("bg_music.mp3", "wb") as f: f.write(r_music.content)
        bg = AudioFileClip("bg_music.mp3").volumex(0.12).set_duration(audio.duration)
        
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
        return "out.mp4", mood
    except Exception as e: return str(e), None

@bot.message_handler(commands=['video'])
def handle(message):
    args = message.text.split(maxsplit=1)
    topic = args[1] if len(args) > 1 else "calm nature"
    bot.reply_to(message, f"🎬 '{topic}' işleniyor. Ruh hali analiz ediliyor...")
    
    # Gemini 2.5 Flash Senaryo
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    # Konuya göre hikaye tipini Gemini belirliyor
    prompt = f"Write a 120 word viral story about {topic}. Make it very emotional or intense."
    script_resp = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]})
    script = script_resp.json()['candidates'][0]['content']['parts'][0]['text']
    
    res, mood = build_video(topic, script)
    if "out.mp4" in res:
        with open(res, 'rb') as v: 
            bot.send_video(message.chat.id, v, caption=f"✨ Mood: {mood.upper()}\n📝 Konu: {topic}")
    else: bot.reply_to(message, f"Hata: {res}")

bot.polling()
