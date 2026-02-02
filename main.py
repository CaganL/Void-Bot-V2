import os
import telebot

# --- KRİTİK YAMA (ANTIALIAS FIX) ---
# MoviePy ve Pillow sürümleri arasındaki uyumsuzluğu giderir
import PIL.Image
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS

import requests
import random
import asyncio
import edge_tts
import numpy as np
import textwrap
import google.generativeai as genai
from PIL import ImageDraw, ImageFont # PIL.Image zaten yukarıda import edildi
from moviepy.editor import VideoFileClip, AudioFileClip, ImageClip, CompositeVideoClip

# --- AYARLAR ---
# Telegram token'ını buraya senin verdiğin şekilde ekledim
TELEGRAM_TOKEN = "8395962603:AAFmuGIsQ2DiUD8nV7ysUjkGbsr1dmGlqKo"

# Bu ikisini Railway'deki Variables kısmından çekecek
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

bot = telebot.TeleBot(TELEGRAM_TOKEN)

# --- YAPAY ZEKA (GEMINI) AYARLARI ---
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# --- 1. HAVALI FONT İNDİRİCİ ---
def download_font():
    """İnternetten kalın ve okunaklı 'Oswald' fontunu indirir."""
    font_path = "Oswald-Bold.ttf"
    if not os.path.exists(font_path):
        url = "https://github.com/google/fonts/raw/main/ofl/oswald/Oswald-Bold.ttf"
        try:
            r = requests.get(url)
            with open(font_path, "wb") as f:
                f.write(r.content)
        except: pass
    return font_path

# --- 2. VİRAL SENARYO YAZARI (GEMINI) ---
def generate_script_with_ai(topic):
    """Konuya göre Gemini'den VİRAL olmaya aday, kancalı (hook) metin alır."""
    if not GEMINI_API_KEY:
        return f"Did you know that {topic} is fascinating? (API Key Missing)"
    
    try:
        model = genai.GenerativeModel('gemini-pro')
        
        # PROMPT: TikTok/Shorts için optimize edilmiş, dikkat çekici giriş.
        prompt = (
            f"Write a viral TikTok/Youtube Shorts script about '{topic}'. "
            "Rule 1: Start with a mind-blowing hook or question (e.g., 'Stop scrolling', 'You won't believe'). "
            "Rule 2: Keep it under 35 words (Short and punchy). "
            "Rule 3: Use simple, engaging English. "
            "Rule 4: Do not use emojis, hashtags or scene descriptions. Just the spoken text."
        )
        
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        return f"Did you know facts about {topic} are amazing? (AI Error: {e})"

# --- 3. ÖZEL ALTYAZI ÇİZERİ (ImageMagick GEREKTİRMEZ) ---
def create_text_image_clip(text, duration, video_size):
    W, H = video_size
    font_path = download_font()
    
    # Font boyutu videonun genişliğine göre dinamik ayarlanır
    fontsize = int(W / 11) 
    
    try: font = ImageFont.truetype(font_path, fontsize)
    except: font = ImageFont.load_default()

    # Metni ekrana sığdır (Text Wrap)
    char_width = fontsize * 0.45 
    max_chars = int((W * 0.9) / char_width)
    wrapper = textwrap.TextWrapper(width=max_chars) 
    word_list = wrapper.wrap(text=text)
    caption_new = '\n'.join(word_list)
    
    # Şeffaf Tuval Oluştur
    img = PIL.Image.new('RGBA', (int(W), int(H)), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Yazıyı Ortala
    bbox = draw.textbbox((0, 0), caption_new, font=font)
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x_pos, y_pos = (W - text_w) / 2, (H - text_h) / 2
    
    # ÇİZİM: Kalın Siyah Kontür + Beyaz Yazı (Okunabilirlik Garantisi)
    draw.text((x_pos, y_pos), caption_new, font=font, fill="white", align="center", stroke_width=5, stroke_fill="black")
    
    # MoviePy Klibine Çevir
    return ImageClip(np.array(img)).set_duration(duration)

# --- 4. SESLENDİRME ---
async def generate_voice_over(text, output_file="voiceover.mp3"):
    communicate = edge_tts.Communicate(text, "en-US-ChristopherNeural")
    await communicate.save(output_file)

# --- 5. STOK VİDEO BULUCU ---
def get_stock_footage(query, duration):
    if not PEXELS_API_KEY: return None
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

# --- 6. VİDEO BİRLEŞTİRME MOTORU ---
def create_video(topic, ai_text):
    try:
        # A. Ses Oluştur
        asyncio.run(generate_voice_over(ai_text))
        
        # B. Video İndir
        video_path = get_stock_footage(topic, 10)
        if not video_path: return "Video bulunamadı."

        # C. Montaj Başlasın
        audio = AudioFileClip("voiceover.mp3")
        video = VideoFileClip(video_path).subclip(0, audio.duration)
        
        # RAM DOSTU OPTİMİZASYON (Çok Önemli!)
        # Videoyu küçültüyoruz ki sunucu çökmesin (960p dikey HD)
        if video.h > 960: video = video.resize(height=960)
        
        # 9:16 Kırpma (Tam Ekran Olması İçin)
        w, h = video.size
        target_ratio = 9/16
        if w / h > target_ratio:
            new_w = h * target_ratio
            video = video.crop(x1=(w/2 - new_w/2), width=new_w, height=h)
        
        video = video.set_audio(audio)
        
        # D. Altyazı Ekleme (Özel Fonksiyon ile)
        try:
            txt_clip = create_text_image_clip(ai_text, video.duration, video.size)
            final_video = CompositeVideoClip([video, txt_clip])
        except Exception as e:
            print(f"Yazı hatası: {e}")
            final_video = video

        output_path = "final_short.mp4"
        
        # E. Render (Hızlı ve Güvenli Mod)
        final_video.write_videofile(output_path, codec="libx264", audio_codec="aac", fps=24, preset='ultrafast', threads=1)
        
        # Temizlik
        video.close()
        audio.close()
        return output_path
    except Exception as e:
        return f"Hata: {str(e)}"

# --- TELEGRAM KOMUTLARI ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "🎬 Video Botu Hazır!\n\nKullanım:\n/video [konu]\n\nÖrnekler:\n/video horror\n/video psychology\n/video space")

@bot.message_handler(commands=['video'])
def handle_video_command(message):
    # Komuttan konuyu ayıkla
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        bot.reply_to(message, "⚠️ Lütfen bir konu yaz.\nÖrnek: `/video korku`")
        return

    topic = args[1] # Kullanıcının konusu
    
    bot.reply_to(message, f"🤖 Konu: '{topic}'\n🧠 Yapay zeka senaryoyu yazıyor ve video hazırlanıyor...\n⏳ (Ortalama 1-2 dakika)")
    
    # 1. Gemini'ye Viral Senaryo Yazdır
    ai_script = generate_script_with_ai(topic)
    
    # 2. Videoyu Üret
    result = create_video(topic, ai_script)
    
    # 3. Sonucu Gönder
    if result and "Hata" in result:
        bot.reply_to(message, f"❌ {result}")
    elif result:
        with open(result, 'rb') as v:
            bot.send_video(message.chat.id, v, caption=f"🎥 **Konu:** {topic}\n📜 **Metin:** {ai_script}")
    else:
        bot.reply_to(message, "Video oluşturulamadı.")

print("Bot çalışıyor...")
bot.polling()
