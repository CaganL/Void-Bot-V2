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
    headers = {"Authorization": PEXELS_API_KEY}
    url = f"https://api.pexels.com/videos/search?query={query}&per_page=5&orientation=portrait"
    r = requests.get(url, headers=headers)
    data = r.json()
    video_files = []
    for video in data.get("videos", []):
        files = video.get("video_files", [])
        if files:
            best_file = max(files, key=lambda x: x["width"] * x["height"])
            video_files.append(best_file["link"])
    
    if not video_files:
        return None
    
    selected_video = random.choice(video_files)
    video_path = "input_video.mp4"
    with open(video_path, "wb") as f:
        f.write(requests.get(selected_video).content)
    return video_path

def create_video():
    try:
        # 1. Ses Oluştur
        asyncio.run(generate_voice_over(TEXT))
        
        # 2. Video İndir
        video_path = get_stock_footage(TOPIC, 10)
        if not video_path:
            return None

        # 3. Klipleri Hazırla
        audio = AudioFileClip("voiceover.mp3")
        
        # --- RAM TASARRUFU 1: Videoyu Yeniden Boyutlandır ---
        # Yüksek çözünürlüklü videoyu işlemek RAM'i bitirir. Boyutu 540p-960p civarına çekiyoruz.
        video = VideoFileClip(video_path).subclip(0, audio.duration)
        video = video.resize(height=960) # Dikey HD kalitesi (Hafıza dostu)
        video = video.crop(x1=video.w/2-270, y1=0, width=540, height=960) # Tam dikey ortala
        
        video = video.set_audio(audio)
        
        # 4. Altyazı Ekle
        try:
            # Font boyutu ve rengi
            txt_clip = TextClip(TEXT, fontsize=40, color='white', font='Arial', size=(500, None), method='caption')
            txt_clip = txt_clip.set_pos('center').set_duration(video.duration)
            final_video = CompositeVideoClip([video, txt_clip])
        except Exception as e:
            print(f"Altyazı hatası: {e}")
            final_video = video

        output_path = "final_short.mp4"
        
        # --- RAM TASARRUFU 2: preset='ultrafast' ve threads=1 ---
        # Bu ayarlar render işlemini hafifletir ve RAM patlamasını önler.
        final_video.write_videofile(
            output_path, 
            codec="libx264", 
            audio_codec="aac", 
            fps=24, 
            preset='ultrafast', 
            threads=1
        )
        
        # Temizlik
        video.close()
        audio.close()
        
        return output_path
        
    except Exception as e:
        print(f"Genel Hata: {str(e)}")
        return None

@bot.message_handler(commands=['start', 'video'])
def send_welcome(message):
    bot.reply_to(message, "Video hazırlanıyor... (RAM dostu modda) ☕")
    
    try:
        video_file = create_video()
        if video_file:
            with open(video_file, 'rb') as v:
                bot.send_video(message.chat.id, v, caption="İşte videon hazır! 🎬")
        else:
            bot.reply_to(message, "Video oluşturulurken bir hata oldu.")
    except Exception as e:
        bot.reply_to(message, f"Hata: {str(e)}")

print("Bot çalışıyor...")
bot.polling()
