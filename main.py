import os
import telebot
import requests
import random
import asyncio
import edge_tts
import numpy as np
import textwrap
from PIL import Image, ImageDraw, ImageFont 
# Hata almamak için doğru içe aktarma
from moviepy.editor import VideoFileClip, AudioFileClip, ImageClip, CompositeVideoClip, concatenate_videoclips

# --- AYARLAR ---
# Token tırnak içinde, boşluksuz olmalı!
TELEGRAM_TOKEN = "8395962603:AAFmuGIsQ2DiUD8nV7ysUjkGbsr1dmGlqKo"
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

bot = telebot.TeleBot(TELEGRAM_TOKEN)

# Pillow Antialias Fix
if not hasattr(Image, 'ANTIALIAS'):
    Image.ANTIALIAS = Image.LANCZOS

def download_font():
    font_path = "Oswald-Bold.ttf"
    if not os.path.exists(font_path):
        url = "https://github.com/google/fonts/raw/main/ofl/oswald/Oswald-Bold.ttf"
        try:
            r = requests.get(url)
            with open(font_path, "wb") as f: f.write(r.content)
        except: pass
    return font_path

# --- 1. SENARYO MOTORU (GEMINI 2.5 FLASH) ---
def get_script(topic):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    # Uzun video için 110-120 kelime istiyoruz (yaklaşık 50 saniye)
    prompt = (f"Write a viral, scary horror story about '{topic}' for a YouTube Short. "
              "Must be 110-120 words. Use simple English and suspenseful tone. Just the story.")
    try:
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        response = requests.post(url, json=payload, timeout=12)
        if response.status_code == 200:
            return response.json()['candidates'][0]['content']['parts'][0]['text'].strip()
    except: pass
    return "The silence in the old house was broken only by the sound of dripping water. But I was alone, and there were no pipes in the attic. Then, the scratching started right under my feet."

# --- 2. ÇOKLU VİDEO İNDİRİCİ ---
def get_multiple_videos(query, total_duration):
    headers = {"Authorization": PEXELS_API_KEY}
    search_url = f"https://api.pexels.com/videos/search?query={query}&per_page=10&orientation=portrait"
    
    try:
        r = requests.get(search_url, headers=headers)
        videos_data = r.json().get("videos", [])
        if not videos_data: return None
        
        downloaded_paths = []
        current_dur = 0
        
        # En fazla 5 farklı sahne indir
        for i, v in enumerate(videos_data[:5]):
            if current_dur >= total_duration: break
            
            # En iyi kalite linkini bul
            link = max(v["video_files"], key=lambda x: x["height"])["link"]
            path = f"part_{i}.mp4"
            with open(path, "wb") as f: f.write(requests.get(link).content)
            
            clip = VideoFileClip(path)
            downloaded_paths.append(path)
            current_dur += clip.duration
            clip.close()
            
        return downloaded_paths
    except: return None

# --- 3. AKILLI ALTYAZI SİSTEMİ ---
def create_subtitles(text, total_duration, video_size):
    W, H = video_size
    font_path = download_font()
    fontsize = int(W / 12) # Büyük ve okunaklı
    try: font = ImageFont.truetype(font_path, fontsize)
    except: font = ImageFont.load_default()

    # Cümle bazlı bölme (Daha profesyonel akış)
    sentences = text.replace(".", ".|").replace("?", "?|").replace("!", "!|").split("|")
    chunks = [s.strip() for s in sentences if s.strip()]
    duration_per_chunk = total_duration / len(chunks)
    
    clips = []
    for chunk in chunks:
        img = Image.new('RGBA', (int(W), int(H)), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        # Metni sığdır
        wrapper = textwrap.TextWrapper(width=int(W/20)) # Genişliğe göre ayar
        caption_wrapped = '\n'.join(wrapper.wrap(text=chunk))
        
        bbox = draw.textbbox((0, 0), caption_wrapped, font=font)
        tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
        
        # Konum: Orta-Alt (Reels butonlarına takılmaz)
        draw.text(((W-tw)/2, H*0.7), caption_wrapped, font=font, fill="#FFD700", align="center", stroke_width=4, stroke_fill="black")
        clips.append(ImageClip(np.array(img)).set_duration(duration_per_chunk))
        
    return concatenate_videoclips(clips)

# --- 4. MONTAJ VE FİNAL ---
def build_video(topic, script):
    try:
        # 1. Seslendirme
        asyncio.run(edge_tts.Communicate(script, "en-US-ChristopherNeural").save("voice.mp3"))
        audio = AudioFileClip("voice.mp3")
        
        # 2. Sahneleri İndir ve Hazırla
        paths = get_multiple_videos(topic, audio.duration)
        if not paths: return "Görüntü bulunamadı."
        
        video_clips = []
        for p in paths:
            c = VideoFileClip(p)
            # Boyutlandırma (9:16)
            if c.h > 1080: c = c.resize(height=1080)
            w, h = c.size
            if w/h > 9/16:
                nw = h * (9/16)
                c = c.crop(x1=(w/2 - nw/2), width=nw, height=h)
            video_clips.append(c)
            
        # 3. Sahneleri Birleştir
        final_video = concatenate_videoclips(video_clips, method="compose")
        
        # Süre kontrolü
        if final_video.duration < audio.duration:
            final_video = final_video.loop(duration=audio.duration)
        else:
            final_video = final_video.subclip(0, audio.duration)
            
        final_video = final_video.set_audio(audio)
        
        # 4. Altyazıları Ekle
        subs = create_subtitles(script, final_video.duration, final_video.size)
        result = CompositeVideoClip([final_video, subs])
        
        # 5. Render
        result.write_videofile("final.mp4", codec="libx264", audio_codec="aac", fps=24, preset='ultrafast', threads=1)
        
        # Temizlik
        for c in video_clips: c.close()
        audio.close()
        return "final.mp4"
    except Exception as e: return f"Hata: {str(e)}"

@bot.message_handler(commands=['video'])
def handle_video(message):
    args = message.text.split(maxsplit=1)
    topic = args[1] if len(args) > 1 else "mystery"
    bot.reply_to(message, f"🎬 '{topic}' konusu için profesyonel montaj başladı... (50-60 saniye sürebilir)")
    
    script = get_script(topic)
    video_file = build_video(topic, script)
    
    if "final" in video_file:
        with open(video_file, 'rb') as v:
            bot.send_video(message.chat.id, v, caption=f"🎥 **Konu:** {topic}")
    else:
        bot.reply_to(message, video_file)

bot.polling()
