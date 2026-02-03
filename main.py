import os
import telebot
import requests
import random
import asyncio
import edge_tts
import numpy as np
import textwrap
from PIL import Image, ImageDraw, ImageFont 
# Doğru MoviePy fonksiyonlarını içeri aktar
from moviepy.editor import VideoFileClip, AudioFileClip, ImageClip, CompositeVideoClip, concatenate_videoclips

# --- AYARLAR ---
# Token'ı tırnak içinde, başında veya sonunda boşluk kalmayacak şekilde yazdım.
TELEGRAM_TOKEN = "8395962603:AAFmuGIsQ2DiUD8nV7ysUjkGbsr1dmGlqKo"
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

bot = telebot.TeleBot(TELEGRAM_TOKEN)

# Pillow Antialias Uyumluluğu
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
    # 40-60 saniye için 115-125 kelime arası hikaye istiyoruz.
    prompt = (f"Write a viral and terrifying horror story about '{topic}' for a YouTube Short. "
              "Length must be around 115-125 words. No intro or outro. Simple English only.")
    try:
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        response = requests.post(url, json=payload, timeout=12)
        if response.status_code == 200:
            return response.json()['candidates'][0]['content']['parts'][0]['text'].strip()
    except: pass
    return "I looked into the baby monitor and saw my son sleeping. Then, a hand reached out from under his bed and stroked his hair. I was home alone with him."

# --- 2. ÇOKLU VİDEO İNDİRİCİ (SAHNE SİSTEMİ) ---
def get_multiple_videos(query, total_duration):
    headers = {"Authorization": PEXELS_API_KEY}
    search_url = f"https://api.pexels.com/videos/search?query={query}&per_page=12&orientation=portrait"
    
    try:
        r = requests.get(search_url, headers=headers)
        videos_data = r.json().get("videos", [])
        if not videos_data: return None
        
        paths = []
        current_dur = 0
        
        # En fazla 5 farklı sahne indirerek akıcılık sağlıyoruz.
        for i, v in enumerate(videos_data[:5]):
            if current_dur >= total_duration: break
            link = max(v["video_files"], key=lambda x: x["height"])["link"]
            path = f"part_{i}.mp4"
            with open(path, "wb") as f: f.write(requests.get(link).content)
            
            clip = VideoFileClip(path)
            paths.append(path)
            current_dur += clip.duration
            clip.close()
            
        return paths
    except: return None

# --- 3. HD ALTYAZI SİSTEMİ ---
def create_subtitles(text, total_duration, video_size):
    W, H = video_size
    font_path = download_font()
    fontsize = int(W / 12) 
    try: font = ImageFont.truetype(font_path, fontsize)
    except: font = ImageFont.load_default()

    sentences = text.replace(".", ".|").replace("?", "?|").replace("!", "!|").split("|")
    chunks = [s.strip() for s in sentences if s.strip()]
    duration_per_chunk = total_duration / len(chunks)
    
    clips = []
    for chunk in chunks:
        img = Image.new('RGBA', (int(W), int(H)), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        wrapper = textwrap.TextWrapper(width=int(W/22))
        caption_wrapped = '\n'.join(wrapper.wrap(text=chunk))
        
        bbox = draw.textbbox((0, 0), caption_wrapped, font=font)
        tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
        
        # Konum: Orta-Alt (Güvenli Alan)
        draw.text(((W-tw)/2, H*0.7), caption_wrapped, font=font, fill="#FFD700", align="center", stroke_width=4, stroke_fill="black")
        clips.append(ImageClip(np.array(img)).set_duration(duration_per_chunk))
        
    return concatenate_videoclips(clips)

# --- 4. MONTAJ MOTORU (HD & COMPATIBLE) ---
def build_video(topic, script):
    try:
        # Seslendirme oluşturma
        asyncio.run(edge_tts.Communicate(script, "en-US-ChristopherNeural").save("voice.mp3"))
        audio = AudioFileClip("voice.mp3")
        
        # Videoları indir
        paths = get_multiple_videos(topic, audio.duration)
        if not paths: return "Görüntü bulunamadı."
        
        video_clips = []
        for p in paths:
            c = VideoFileClip(p)
            # Boyutlandırma ve 9:16 Kırpma
            if c.h > 1080: c = c.resize(height=1080)
            w, h = c.size
            if w/h > 9/16:
                nw = h * (9/16)
                c = c.crop(x1=(w/2 - nw/2), width=nw, height=h)
            video_clips.append(c)
            
        # Sahneleri uç uca birleştir
        main_video = concatenate_videoclips(video_clips, method="compose")
        
        # Süreyi sese uyarla (Loop veya Subclip)
        if main_video.duration < audio.duration:
            main_video = main_video.loop(duration=audio.duration)
        else:
            main_video = main_video.subclip(0, audio.duration)
            
        main_video = main_video.set_audio(audio)
        
        # Altyazıları hazırla ve üzerine ekle
        subs = create_subtitles(script, main_video.duration, main_video.size)
        final_result = CompositeVideoClip([main_video, subs])
        
        # TELEGRAM UYUMLU RENDER ( pix_fmt yuv420p siyah ekranı çözer )
        final_result.write_videofile(
            "final_video.mp4", 
            codec="libx264", 
            audio_codec="aac", 
            fps=24, 
            preset='ultrafast', 
            ffmpeg_params=["-pix_fmt", "yuv420p"],
            threads=4
        )
        
        # Bellek temizliği
        for c in video_clips: c.close()
        audio.close()
        return "final_video.mp4"
    except Exception as e: return f"Hata detayı: {str(e)}"

@bot.message_handler(commands=['video'])
def handle_video(message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(message, "Lütfen bir konu yaz. Örnek: `/video abandoned house`")
        return
        
    topic = args[1]
    bot.reply_to(message, f"🎥 '{topic}' konusu üzerine profesyonel kurgu başladı. 1-2 dakika sürebilir...")
    
    script = get_script(topic)
    video_path = build_video(topic, script)
    
    if "final_video" in video_path:
        with open(video_path, 'rb') as v:
            bot.send_video(message.chat.id, v, caption=f"🎬 **Konu:** {topic}")
    else:
        bot.reply_to(message, f"❌ Bir sorun oluştu: {video_path}")

bot.polling()
