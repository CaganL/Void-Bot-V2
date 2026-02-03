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

# --- AYARLAR ---
TELEGRAM_TOKEN = "8395962603:AAFmuGIs (token buraya)"
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

bot = telebot.TeleBot(TELEGRAM_TOKEN)

# --- FONT & YAMA ---
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

# --- 1. SENARYO (GEMINI 2.5) ---
def get_script(topic):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    prompt = f"Write a terrifying or engaging story about '{topic}' for a YouTube Short. Approx 110 words. Simple English."
    try:
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        response = requests.post(url, json=payload, timeout=10)
        return response.json()['candidates'][0]['content']['parts'][0]['text'].strip()
    except:
        return "Did you know your brain makes decisions before you even realize it? You think you chose to watch this, but it was already decided for you."

# --- 2. AKILLI ALTYAZI (HD & KONUM) ---
def create_dynamic_subtitles(text, total_duration, video_size):
    W, H = video_size
    font_path = download_font()
    fontsize = int(W / 12) # Biraz daha büyük font
    try: font = ImageFont.truetype(font_path, fontsize)
    except: font = ImageFont.load_default()

    sentences = text.replace(".", ".|").replace("?", "?|").replace("!", "!|").split("|")
    chunks = [s.strip() for s in sentences if s.strip()]
    duration_per_chunk = total_duration / len(chunks)
    
    clips = []
    for chunk in chunks:
        # Daha yüksek çözünürlüklü çizim için W*2 yapıp sonra resize edebiliriz ama bu basit kalsın
        img = Image.new('RGBA', (int(W), int(H)), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        char_width = fontsize * 0.45 
        max_chars = int((W * 0.8) / char_width)
        wrapper = textwrap.TextWrapper(width=max_chars)
        caption_new = '\n'.join(wrapper.wrap(text=chunk))
        
        bbox = draw.textbbox((0, 0), caption_new, font=font)
        x_pos, y_pos = (W - (bbox[2]-bbox[0]))/2, (H * 0.65) # Biraz daha yukarıda
        
        draw.text((x_pos, y_pos), caption_new, font=font, fill="#FFD700", align="center", stroke_width=4, stroke_fill="black")
        clips.append(ImageClip(np.array(img)).set_duration(duration_per_chunk))
        
    return concatenate_videoclips(clips)

# --- 3. ÇOKLU VİDEO İNDİRİCİ (MULTIPLE CLIPS) ---
def get_multiple_videos(query, total_duration):
    headers = {"Authorization": PEXELS_API_KEY}
    search_url = f"https://api.pexels.com/videos/search?query={query}&per_page=10&orientation=portrait"
    
    try:
        r = requests.get(search_url, headers=headers)
        videos = r.json().get("videos", [])
        if not videos: return None
        
        video_paths = []
        current_dur = 0
        
        # Gerektiği kadar video indir
        for i, v in enumerate(videos[:5]): # Maksimum 5 farklı klip
            if current_dur >= total_duration: break
            
            best_file = max(v["video_files"], key=lambda x: x["height"])["link"]
            path = f"part_{i}.mp4"
            with open(path, "wb") as f: f.write(requests.get(best_file).content)
            
            temp_clip = VideoFileClip(path)
            video_paths.append(path)
            current_dur += temp_clip.duration
            temp_clip.close()
            
        return video_paths
    except: return None

# --- 4. MONTAJ ---
def create_video(topic, script):
    try:
        asyncio.run(edge_tts.Communicate(script, "en-US-ChristopherNeural").save("voiceover.mp3"))
        audio = AudioFileClip("voiceover.mp3")
        
        # Birden fazla video klipi al
        paths = get_multiple_videos(topic, audio.duration)
        if not paths: return "Video bulunamadı."
        
        clips = []
        for p in paths:
            c = VideoFileClip(p)
            # Boyutlandırma
            if c.h > 960: c = c.resize(height=960)
            # 9:16 Kırpma
            w, h = c.size
            if w/h > 9/16:
                new_w = h * (9/16)
                c = c.crop(x1=(w/2 - new_w/2), width=new_w, height=h)
            clips.append(c)
            
        # Klip'leri uç uca ekle
        full_video = concatenate_videoclips(clips, method="compose")
        
        # Eğer videolar hala sesden kısaysa loop yap
        if full_video.duration < audio.duration:
            full_video = full_video.loop(duration=audio.duration)
        else:
            full_video = full_video.subclip(0, audio.duration)
            
        full_video = full_video.set_audio(audio)
        subtitle_clip = create_dynamic_subtitles(script, full_video.duration, full_video.size)
        final = CompositeVideoClip([full_video, subtitle_clip])
        
        final.write_videofile("final.mp4", codec="libx264", audio_codec="aac", fps=24, preset='ultrafast', threads=1)
        
        for c in clips: c.close()
        audio.close()
        return "final.mp4"
    except Exception as e: return f"Hata: {str(e)}"

@bot.message_handler(commands=['video'])
def handle_video(message):
    topic = message.text.split(maxsplit=1)[1] if len(message.text.split()) > 1 else "mystery"
    bot.reply_to(message, f"🎬 '{topic}' için çoklu video montajı başlıyor...")
    script = get_script(topic)
    res = create_video(topic, script)
    if "final" in res:
        with open(res, 'rb') as v: bot.send_video(message.chat.id, v, caption=f"Konu: {topic}")
    else: bot.reply_to(message, res)

bot.polling()
