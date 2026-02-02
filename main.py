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
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

bot = telebot.TeleBot(TELEGRAM_TOKEN)

# --- KRİTİK YAMA (ANTIALIAS FIX) ---
if not hasattr(Image, 'ANTIALIAS'):
    Image.ANTIALIAS = Image.LANCZOS

# --- 1. YEDEK SENARYO DEPOSU (FALLBACK) ---
# Eğer Google yine naz yaparsa bot bu hazır metinleri kullanacak.
BACKUP_SCRIPTS = {
    "horror": "Did you know that if you wake up at 3 AM out of nowhere, there is an 80% chance someone is staring at you?",
    "psychology": "Psychology says, if you can't stop thinking about someone, it's because they were thinking about you first.",
    "space": "Did you know that space is completely silent? No matter how loud you scream, no one can hear you die.",
    "love": "Did you know that staring into someone's eyes for 4 minutes can make you fall in love, even with a stranger?",
    "default": "Did you know that your brain makes decisions 7 seconds before you are even conscious of them? You are not in control."
}

# --- 2. FONT İNDİRİCİ ---
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

# --- 3. SENARYO ÜRETİCİ (GEMINI 2.5 FLASH) ---
def get_script(topic):
    # 1. Önce Google'ın En Yeni Modelini Dene
    ai_response = try_google_ai(topic)
    
    if ai_response:
        return ai_response, None # (Senaryo, Hata Yok)
    
    # 2. Hata olursa YEDEK depodan seç
    print("Google AI başarısız oldu, yedek senaryo kullanılıyor.")
    
    topic_lower = topic.lower()
    if "horror" in topic_lower or "scary" in topic_lower or "korku" in topic_lower:
        script = BACKUP_SCRIPTS["horror"]
    elif "space" in topic_lower or "uzay" in topic_lower:
        script = BACKUP_SCRIPTS["space"]
    elif "psychology" in topic_lower or "psikoloji" in topic_lower:
        script = BACKUP_SCRIPTS["psychology"]
    elif "love" in topic_lower or "aşk" in topic_lower:
        script = BACKUP_SCRIPTS["love"]
    else:
        script = BACKUP_SCRIPTS["default"]
        
    return script, "⚠️ Not: AI yanıt vermedi, yedek senaryo devrede."

def try_google_ai(topic):
    if not GEMINI_API_KEY: return None
    
    # İŞTE BURASI! Senin listendeki 'gemini-2.5-flash' modelini kullanıyoruz.
    model_name = "gemini-2.5-flash" 
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
    
    headers = {'Content-Type': 'application/json'}
    
    # Prompt: TikTok tarzı, kancalı, kısa ve emojisisz
    prompt = (
        f"Write a viral TikTok script about '{topic}'. "
        "Start with a mind-blowing hook like 'Did you know'. "
        "Keep it under 35 words. "
        "Simple English. No emojis. Just the text to be spoken."
    )
    
    try:
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        response = requests.post(url, headers=headers, json=payload, timeout=8)
        
        if response.status_code == 200:
            return response.json()['candidates'][0]['content']['parts'][0]['text'].strip()
        else:
            print(f"Google Hata Kodu: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Bağlantı Hatası: {e}")
        
    return None

# --- 4. ALTYAZI ÇİZERİ (SARI & BÜYÜK) ---
def create_text_image_clip(text, duration, video_size):
    W, H = video_size
    font_path = download_font()
    fontsize = int(W / 12) 
    
    try: font = ImageFont.truetype(font_path, fontsize)
    except: font = ImageFont.load_default()

    char_width = fontsize * 0.45 
    max_chars = int((W * 0.90) / char_width)
    wrapper = textwrap.TextWrapper(width=max_chars) 
    word_list = wrapper.wrap(text=text)
    caption_new = '\n'.join(word_list)
    
    img = Image.new('RGBA', (int(W), int(H)), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    bbox = draw.textbbox((0, 0), caption_new, font=font)
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x_pos, y_pos = (W - text_w) / 2, (H - text_h) / 2
    
    # SARI YAZI + KALIN SİYAH ÇERÇEVE
    draw.text((x_pos, y_pos), caption_new, font=font, fill="#FFD700", align="center", stroke_width=6, stroke_fill="black")
    return ImageClip(np.array(img)).set_duration(duration)

# --- 5. DİĞER FONKSİYONLAR ---
async def generate_voice_over(text, output_file="voiceover.mp3"):
    communicate = edge_tts.Communicate(text, "en-US-ChristopherNeural")
    await communicate.save(output_file)

def get_stock_footage(query, duration):
    if not PEXELS_API_KEY: return None
    headers = {"Authorization": PEXELS_API_KEY}
    
    # Arama terimini biraz süsleyelim ki daha iyi video bulsun
    search_query = query
    if "horror" in query.lower(): search_query = "scary dark horror"
    if "space" in query.lower(): search_query = "galaxy stars space"
    
    url = f"https://api.pexels.com/videos/search?query={search_query}&per_page=5&orientation=portrait"
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
        with open("input_video.mp4", "wb") as f:
            f.write(requests.get(selected_video).content)
        return "input_video.mp4"
    except: return None

def create_video(topic, script):
    try:
        asyncio.run(generate_voice_over(script))
        video_path = get_stock_footage(topic, 10)
        
        # Video bulunamazsa yedek video kullan
        if not video_path: video_path = get_stock_footage("dark aesthetic", 10)
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
            txt_clip = create_text_image_clip(script, video.duration, video.size)
            final_video = CompositeVideoClip([video, txt_clip])
        except: final_video = video

        final_video.write_videofile("final_short.mp4", codec="libx264", audio_codec="aac", fps=24, preset='ultrafast', threads=1)
        video.close()
        audio.close()
        return "final_short.mp4"
    except Exception as e: return f"Hata: {str(e)}"

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
    bot.reply_to(message, f"🤖 Konu: '{topic}' işleniyor... (Model: Gemini 2.5)")
    
    # SENARYOYU AL
    script, warning = get_script(topic)
    
    result = create_video(topic, script)
    
    if result and "Hata" in result:
        bot.reply_to(message, f"❌ {result}")
    elif result:
        caption = f"🎥 Konu: {topic}\n📝 Metin: {script}"
        if warning: caption += f"\n\n{warning}"
        
        with open(result, 'rb') as v:
            bot.send_video(message.chat.id, v, caption=caption)

bot.polling()
