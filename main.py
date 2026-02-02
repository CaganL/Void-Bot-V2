import os
import telebot
import shutil

# --- KRİTİK YAMA: ImageMagick'i Otomatik Bul ---
# Sistemde 'convert' veya 'magick' komutunu arar ve bulduğunu kullanır.
magick_path = shutil.which("convert") or shutil.which("magick")
from moviepy.config import change_settings
if magick_path:
    change_settings({"IMAGEMAGICK_BINARY": magick_path})
else:
    print("⚠️ UYARI: ImageMagick bulunamadı! Altyazılar çalışmayabilir.")

# --- PILLOW YAMASI (Eski ANTIALIAS Hatası İçin) ---
import PIL.Image
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS

import requests
import json
import random
import asyncio
import edge_tts
from moviepy.editor import VideoFileClip, AudioFileClip, TextClip, CompositeVideoClip

# --- AYARLAR ---
TELEGRAM_TOKEN = "8395962603:AAFmuGIsQ2DiUD8nV7ysUjkGbsr1dmGlqKo"
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")

bot = telebot.TeleBot(TELEGRAM_TOKEN)

# --- İÇERİK ---
TOPIC = "Fear"
TEXT = "Did you know that fear is just a chemical reaction? Your brain prepares you to fight or flight."

async def generate_voice_over(text, output_file="voiceover.mp3"):
    communicate = edge_tts.Communicate(text, "en-US-ChristopherNeural")
    await communicate.save(output_file)

def get_stock_footage(query, duration):
    headers = {"Authorization": PEXELS_API_KEY}
    url = f"https://api.pexels.com/videos/search?query={query}&per_page=5&orientation=portrait"
    try:
        r = requests.get(url, headers=headers)
        data = r.json()
        video_files = []
        for video in data.get("videos", []):
            files = video.get("video_files", [])
            if files:
                best_file = max(files, key=lambda x: x["width"] * x["height"])
                video_files.append(best_file["link"])
        
        if not video_files: return None
        selected_video = random.choice(video_files)
        video_path = "input_video.mp4"
        with open(video_path, "wb") as f:
            f.write(requests.get(selected_video).content)
        return video_path
    except: return None

def create_video():
    try:
        # 1. Ses
        asyncio.run(generate_voice_over(TEXT))
        
        # 2. Video
        video_path = get_stock_footage(TOPIC, 10)
        if not video_path: return "Video bulunamadı."

        # 3. Montaj
        audio = AudioFileClip("voiceover.mp3")
        video = VideoFileClip(video_path).subclip(0, audio.duration)
        
        # RAM TASARRUFU: Boyut küçültme (60 saniye videoyu kurtaracak hamle bu!)
        if video.h > 960: video = video.resize(height=960)
        
        # 9:16 Kırpma
        w, h = video.size
        target_ratio = 9/16
        if w / h > target_ratio:
            new_w = h * target_ratio
            video = video.crop(x1=(w/2 - new_w/2), width=new_w, height=h)
        
        video = video.set_audio(audio)
        
        # 4. ALTYAZI
        if magick_path: # Sadece araç yüklüyse dene
            try:
                # Linux uyumlu font: DejaVu-Sans
                txt_clip = TextClip(TEXT, fontsize=40, color='white', font='DejaVu-Sans', size=(video.w - 40, None), method='caption')
                txt_clip = txt_clip.set_pos('center').set_duration(video.duration)
                final_video = CompositeVideoClip([video, txt_clip])
            except Exception as e:
                return f"Altyazı Hatası: {str(e)}"
        else:
            final_video = video # Araç yoksa yazısız devam et

        output_path = "final_short.mp4"
        # RAM DOSTU RENDER (THREADS=1 ve ULTRAFAST)
        final_video.write_videofile(output_path, codec="libx264", audio_codec="aac", fps=24, preset='ultrafast', threads=1)
        
        video.close()
        audio.close()
        return output_path
    except Exception as e:
        return f"Genel Hata: {str(e)}"

@bot.message_handler(commands=['start', 'video'])
def send_welcome(message):
    bot.reply_to(message, "Video hazırlanıyor... 🛠️")
    result = create_video()
    
    if result and ("Hata" in result or "bulunamadı" in result):
        bot.reply_to(message, f"❌ {result}")
    elif result:
        with open(result, 'rb') as v:
            bot.send_video(message.chat.id, v, caption="İşlem Tamam! 🎬")
    else:
        bot.reply_to(message, "Bilinmeyen hata.")

bot.polling()
