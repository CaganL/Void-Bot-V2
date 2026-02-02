import os
import telebot

# --- KRİTİK YAMA (ANTIALIAS FIX) ---
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
from PIL import ImageDraw, ImageFont 
from moviepy.editor import VideoFileClip, AudioFileClip, ImageClip, CompositeVideoClip

# --- AYARLAR ---
TELEGRAM_TOKEN = "8395962603:AAFmuGIsQ2DiUD8nV7ysUjkGbsr1dmGlqKo"
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

bot = telebot.TeleBot(TELEGRAM_TOKEN)

# --- YAPAY ZEKA AYARLARI ---
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# --- 1. FONT İNDİRİCİ ---
def download_font():
    font_path = "Oswald-Bold.ttf"
    if not os.path.exists(font_path):
        url = "https://github.com/google/fonts/raw/main/ofl/oswald/Oswald-Bold.ttf"
        try:
            r = requests.get(url)
            with open(font_path, "wb") as f:
                f.write(r.content)
        except: pass
    return font_path

# --- 2. VİRAL SENARYO (GÜNCEL MODEL) ---
def generate_script_with_ai(topic):
    if not GEMINI_API_KEY:
        return f"API Key missing for {topic}."
    
    try:
        # GÜNCEL VE HIZLI MODEL
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        prompt = (
            f"Write a short, engaging script for a viral video about '{topic}'. "
            "Start with a hook like 'Did you know'. "
            "Keep it under 40 words. "
            "Write in simple English. No emojis."
        )
        
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        return f"AI Error: {str(e)}"

# --- 3. ALTYAZI ÇİZERİ (SARI VE BÜYÜK) ---
def create_text_image_clip(text, duration, video_size):
    W, H = video_size
    font_path = download_font()
    
    # Font boyutu: Ekran genişliğinin 12'de 1'i (Büyük ve okunaklı)
    fontsize = int(W / 12) 
    
    try: font = ImageFont.truetype(font_path, fontsize)
    except: font = ImageFont.load_default()

    # Metni sığdır
    char_width = fontsize * 0.45 
    max_chars = int((W * 0.90) / char_width)
    wrapper = textwrap.TextWrapper(width=max_chars) 
    word_list = wrapper.wrap(text=text)
    caption_new = '\n'.join(word_list)
    
    img = PIL.Image.new('RGBA', (int(W), int(H)), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    bbox = draw.textbbox((0, 0), caption_new, font=font)
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x_pos, y_pos = (W - text_w) / 2, (H - text_h) / 2
    
    # SARI YAZI + KALIN SİYAH KENARLIK
    draw.text((x_pos, y_pos), caption_new, font=font, fill="#FFD700", align="center", stroke_width=6, stroke_fill="black")
    
    return ImageClip(np.array(img)).set_duration(duration)

# --- 4. SESLENDİRME ---
async def generate_voice_over(text, output_file="voiceover.mp3"):
    communicate = edge_tts.Communicate(text, "en-US-ChristopherNeural")
    await communicate.save(output_file)

# --- 5. STOK VİDEO ---
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

# --- 6. MONTAJ ---
def create_video(topic, ai_text):
    try:
        asyncio.run(generate_voice_over(ai_text))
        
        # Videoyu bulamazsa yedek olarak "abstract" ara
        video_path = get_stock_footage(topic, 10)
        if not video_path: 
            video_path = get_stock_footage("mystery", 10)
            if not video_path: return "Video bulunamadı."

        audio = AudioFileClip("voiceover.mp3")
        video = VideoFileClip(video_path).subclip(0, audio.duration)
        
        if video.h > 960: video = video.resize(height=960)
        w, h = video.size
        if w/h > 9/16:
            new_w = h * (9/16)
            video = video.crop(x1=(w/2 - new_w/2), width=new_w, height=h)
        
        video = video.set_audio(audio)
        
        try:
            txt_clip = create_text_image_clip(ai_text, video.duration, video.size)
            final_video = CompositeVideoClip([video, txt_clip])
        except Exception as e:
            final_video = video

        output_path = "final_short.mp4"
        final_video.write_videofile(output_path, codec="libx264", audio_codec="aac", fps=24, preset='ultrafast', threads=1)
        
        video.close()
        audio.close()
        return output_path
    except Exception as e:
        return f"Hata: {str(e)}"

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "Hazırız! Örnek: `/video horror`")

@bot.message_handler(commands=['video'])
def handle_video_command(message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(message, "Konu yazmadın. Örnek: `/video horror`")
        return

    topic = args[1]
    bot.reply_to(message, f"🤖 Konu: '{topic}' işleniyor...")
    
    ai_script = generate_script_with_ai(topic)
    
    if "AI Error" in ai_script:
        bot.reply_to(message, f"⚠️ {ai_script}")
        return

    result = create_video(topic, ai_script)
    
    if result and "Hata" in result:
        bot.reply_to(message, f"❌ {result}")
    elif result:
        with open(result, 'rb') as v:
            bot.send_video(message.chat.id, v, caption=f"🎥 Konu: {topic}")

bot.polling()
