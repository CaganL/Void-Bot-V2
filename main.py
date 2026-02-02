import os
import telebot
import requests
import json
import random
import asyncio
import edge_tts
from moviepy.editor import VideoFileClip, AudioFileClip, TextClip, CompositeVideoClip
from moviepy.video.tools.subtitles import SubtitlesClip

# --- AYARLAR ---
TELEGRAM_TOKEN = "8395962603:AAFmuGIsQ2DiUD8nV7ysUjkGbsr1dmGlqKo"
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")

bot = telebot.TeleBot(TELEGRAM_TOKEN)

# --- KONU VE METİN (Basit Test İçin) ---
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
    # 1. Ses Oluştur
    asyncio.run(generate_voice_over(TEXT))
    
    # 2. Video İndir
    video_path = get_stock_footage(TOPIC, 10)
    if not video_path:
        return None

    # 3. Birleştir
    audio = AudioFileClip("voiceover.mp3")
    video = VideoFileClip(video_path).subclip(0, audio.duration)
    video = video.set_audio(audio)
    
    # 4. Altyazı (Basit)
    txt_clip = TextClip(TEXT, fontsize=50, color='white', size=video.size, method='caption')
    txt_clip = txt_clip.set_pos('center').set_duration(video.duration)
    
    final_video = CompositeVideoClip([video, txt_clip])
    output_path = "final_short.mp4"
    final_video.write_videofile(output_path, codec="libx264", audio_codec="aac", fps=24)
    return output_path

@bot.message_handler(commands=['start', 'video'])
def send_welcome(message):
    bot.reply_to(message, "Video hazırlanıyor... Lütfen yaklaşık 1-2 dakika bekle. ☕")
    
    try:
        video_file = create_video()
        if video_file:
            with open(video_file, 'rb') as v:
                bot.send_video(message.chat.id, v, caption="İşte videon hazır! 🎬")
        else:
            bot.reply_to(message, "Video oluşturulurken bir hata oldu.")
    except Exception as e:
        bot.reply_to(message, f"Hata oluştu: {str(e)}")

print("Bot çalışıyor...")
bot.polling()
