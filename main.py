import os
import telebot
import requests
import random
import asyncio
import edge_tts
import numpy as np
import textwrap
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import VideoFileClip, AudioFileClip, ImageClip, CompositeVideoClip

# --- AYARLAR ---
TELEGRAM_TOKEN = "8395962603:AAFmuGIsQ2DiUD8nV7ysUjkGbsr1dmGlqKo"
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")

bot = telebot.TeleBot(TELEGRAM_TOKEN)

# --- İÇERİK ---
TOPIC = "Fear"
TEXT = "Did you know that fear is just a chemical reaction? Your brain prepares you to fight or flight."

# --- ÖZEL FONKSİYON: ImageMagick Olmadan Yazı Yazma ---
def create_text_image_clip(text, duration, video_size, fontsize=40):
    W, H = video_size
    
    # 1. Şeffaf bir resim oluştur (Tuval)
    img = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # 2. Font ayarla (Sistem fontu bulamazsa varsayılanı kullanır)
    try:
        # Linux için yaygın font
        font = ImageFont.truetype("DejaVuSans.ttf", fontsize)
    except:
        try:
            # Alternatif font
            font = ImageFont.truetype("arial.ttf", fontsize)
        except:
            # Hiçbiri yoksa varsayılan (biraz çirkin olabilir ama çalışır)
            font = ImageFont.load_default()
    
    # 3. Metni ekrana sığacak şekilde parçala (Wrap)
    # Ortalama her satıra 20-25 karakter sığar (fontsize'a göre değişir)
    char_width = 20 
    wrapper = textwrap.TextWrapper(width=int(W / char_width)) 
    word_list = wrapper.wrap(text=text)
    caption_new = '\n'.join(word_list)
    
    # 4. Yazıyı ortala ve çiz
    # Metnin kaplayacağı alanı hesapla (kabaca)
    text_w, text_h = draw.textbbox((0, 0), caption_new, font=font)[2:]
    
    x_pos = (W - text_w) / 2
    y_pos = (H - text_h) / 2
    
    # Siyah gölge (okunabilirlik için)
    draw.text((x_pos+2, y_pos+2), caption_new, font=font, fill="black", align="center")
    # Beyaz yazı
    draw.text((x_pos, y_pos), caption_new, font=font, fill="white", align="center")
    
    # 5. Resmi MoviePy klibine çevir
    return ImageClip(np.array(img)).set_duration(duration)

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
        
        # RAM TASARRUFU
        if video.h > 960: video = video.resize(height=960)
        
        w, h = video.size
        target_ratio = 9/16
        if w / h > target_ratio:
            new_w = h * target_ratio
            video = video.crop(x1=(w/2 - new_w/2), width=new_w, height=h)
        
        video = video.set_audio(audio)
        
        # 4. ALTYAZI (YENİ GÜVENLİ YÖNTEM)
        try:
            # Artık TextClip yok, özel fonksiyonumuz var
            txt_clip = create_text_image_clip(TEXT, video.duration, video.size)
            final_video = CompositeVideoClip([video, txt_clip])
        except Exception as e:
            print(f"Yazı hatası: {e}")
            final_video = video

        output_path = "final_short.mp4"
        final_video.write_videofile(output_path, codec="libx264", audio_codec="aac", fps=24, preset='ultrafast', threads=1)
        
        video.close()
        audio.close()
        return output_path
    except Exception as e:
        return f"Genel Hata: {str(e)}"

@bot.message_handler(commands=['start', 'video'])
def send_welcome(message):
    bot.reply_to(message, "Video hazırlanıyor... (ImageMagick'siz Özel Mod) 🎨")
    result = create_video()
    
    if result and ("Hata" in result or "bulunamadı" in result):
        bot.reply_to(message, f"❌ {result}")
    elif result:
        with open(result, 'rb') as v:
            bot.send_video(message.chat.id, v, caption="Zafer bizimdir! 🎬")
    else:
        bot.reply_to(message, "Bilinmeyen hata.")

bot.polling()
