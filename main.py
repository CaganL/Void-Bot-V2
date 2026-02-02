import os
import telebot
# --- MOVIEPY AYARLARI ---
from moviepy.config import change_settings
change_settings({"IMAGEMAGICK_BINARY": "convert"})

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

# --- SABİT TEST İÇERİĞİ ---
TOPIC = "Fear"
TEXT = "Did you know that fear is just a chemical reaction? Your brain prepares you to fight or flight."

async def generate_voice_over(text, output_file="voiceover.mp3"):
    communicate = edge_tts.Communicate(text, "en-US-ChristopherNeural")
    await communicate.save(output_file)

def get_stock_footage(query, duration):
    if not PEXELS_API_KEY:
        raise Exception("PEXELS_API_KEY bulunamadı! Railway Variables ayarını kontrol et.")
        
    headers = {"Authorization": PEXELS_API_KEY}
    url = f"https://api.pexels.com/videos/search?query={query}&per_page=5&orientation=portrait"
    r = requests.get(url, headers=headers)
    
    if r.status_code != 200:
        raise Exception(f"Pexels Hatası: {r.status_code} - {r.text}")
        
    data = r.json()
    video_files = []
    for video in data.get("videos", []):
        files = video.get("video_files", [])
        if files:
            best_file = max(files, key=lambda x: x["width"] * x["height"])
            video_files.append(best_file["link"])
    
    if not video_files:
        raise Exception("Pexels video bulamadı. Konu veya API ile ilgili sorun olabilir.")
    
    selected_video = random.choice(video_files)
    video_path = "input_video.mp4"
    with open(video_path, "wb") as f:
        f.write(requests.get(selected_video).content)
    return video_path

def create_video():
    # 1. Ses Oluştur
    asyncio.run(generate_voice_over(TEXT))
    
    # 2. Video İndir
    video_path = get_stock_footage(TOPIC, 10)

    # 3. Klipleri Hazırla
    audio = AudioFileClip("voiceover.mp3")
    
    # RAM Tasarrufu: Videoyu küçült
    video = VideoFileClip(video_path).subclip(0, audio.duration)
    # Hedef yükseklik 960 (Dikey HD'den biraz düşük, hafıza dostu)
    if video.h > 960:
        video = video.resize(height=960) 
    
    # Kırpma (Crop) işlemi - 9:16 formatı için
    w, h = video.size
    target_ratio = 9/16
    if w / h > target_ratio:
        # Video çok geniş, yanlardan kırp
        new_w = h * target_ratio
        video = video.crop(x1=(w/2 - new_w/2), width=new_w, height=h)
    
    video = video.set_audio(audio)
    
    # 4. Altyazı Ekle
    try:
        txt_clip = TextClip(TEXT, fontsize=40, color='white', size=(video.w - 40, None), method='caption')
        txt_clip = txt_clip.set_pos('center').set_duration(video.duration)
        final_video = CompositeVideoClip([video, txt_clip])
    except Exception as e:
        # Altyazı hatası olursa videosuz devam et
        final_video = video

    output_path = "final_short.mp4"
    
    # Render (Ultrafast + Threads 1 = RAM Dostu)
    final_video.write_videofile(
        output_path, 
        codec="libx264", 
        audio_codec="aac", 
        fps=24, 
        preset='ultrafast', 
        threads=1
    )
    
    video.close()
    audio.close()
    return output_path

@bot.message_handler(commands=['start', 'video'])
def send_welcome(message):
    bot.reply_to(message, "Video hazırlanıyor... (Debug Modu Açık) 🐞")
    
    try:
        video_file = create_video()
        with open(video_file, 'rb') as v:
            bot.send_video(message.chat.id, v, caption="İşte videon hazır! 🎬")
    except Exception as e:
        # HATAYI BURADA YAKALAYIP SANA GÖNDERECEK
        bot.reply_to(message, f"❌ HATA DETAYI:\n{str(e)}")

print("Bot çalışıyor...")
bot.polling()
