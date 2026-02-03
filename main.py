import os
import telebot
import requests
import random
import asyncio
import edge_tts
import numpy as np
import textwrap
from PIL import Image, ImageDraw, ImageFont 
# DÜZELTME: ConcatenateVideoClip yerine concatenate_videoclips eklendi
from moviepy.editor import VideoFileClip, AudioFileClip, ImageClip, CompositeVideoClip, concatenate_videoclips

# --- AYARLAR ---
TELEGRAM_TOKEN = "8395962603:AAFmuGIsQ2DiUD8nV7ysUjkGbsr1dmGlqKo"
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

bot = telebot.TeleBot(TELEGRAM_TOKEN)

# --- KRİTİK YAMA (ANTIALIAS FIX) ---
if not hasattr(Image, 'ANTIALIAS'):
    Image.ANTIALIAS = Image.LANCZOS

# --- 1. YEDEK SENARYO DEPOSU (FALLBACK) ---
BACKUP_SCRIPTS = {
    "horror": "They say if you wake up at 3 AM, someone is watching you. But the scariest part isn't the eyes you feel on your back. It's the fact that when you look in the mirror, your reflection blinks a second later than you do. Try it tonight.",
    "space": "Space is not just empty. It's silent. If you screamed in space, even if someone was right next to you, they wouldn't hear a thing. You would die in absolute, terrifying silence.",
    "default": "Your brain makes decisions 7 seconds before you are conscious of them. So when you think you chose to watch this video, your subconscious had already decided for you. You are not in control."
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

# --- 3. UZUN SENARYO ÜRETİCİ (GEMINI 2.5) ---
def get_script(topic):
    ai_response = try_google_ai(topic)
    if ai_response:
        return ai_response, None
    
    topic_lower = topic.lower()
    if "horror" in topic_lower: script = BACKUP_SCRIPTS["horror"]
    elif "space" in topic_lower: script = BACKUP_SCRIPTS["space"]
    else: script = BACKUP_SCRIPTS["default"]
        
    return script, "⚠️ Not: AI yanıt vermedi, yedek hikaye kullanıldı."

def try_google_ai(topic):
    if not GEMINI_API_KEY: return None
    
    model_name = "gemini-2.5-flash" 
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
    headers = {'Content-Type': 'application/json'}
    
    prompt = (
        f"Write a viral, scary or engaging story about '{topic}' for a YouTube Short. "
        "It must be approximately 100 to 120 words long (approx 45-60 seconds spoken). "
        "Do not write intro or outro. Just the story. Simple English."
    )
    
    try:
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        if response.status_code == 200:
            return response.json()['candidates'][0]['content']['parts'][0]['text'].strip()
    except: pass
    return None

# --- 4. AKILLI ALTYAZI SİSTEMİ (PARÇALI) ---
def create_dynamic_subtitles(text, total_duration, video_size):
    W, H = video_size
    font_path = download_font()
    fontsize = int(W / 14) 
    try: font = ImageFont.truetype(font_path, fontsize)
    except: font = ImageFont.load_default()

    # Metni Cümlelere Böl
    sentences = text.replace(".", ".|").replace("?", "?|").replace("!", "!|").split("|")
    chunks = [s.strip() for s in sentences if s.strip()]
    
    if len(chunks) < 3:
        words = text.split()
        chunk_size = 15 
        chunks = [' '.join(words[i:i+chunk_size]) for i in range(0, len(words), chunk_size)]

    duration_per_chunk = total_duration / len(chunks)
    
    clips = []
    
    for chunk in chunks:
        img = Image.new('RGBA', (int(W), int(H)), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        char_width = fontsize * 0.45 
        max_chars = int((W * 0.85) / char_width)
        wrapper = textwrap.TextWrapper(width=max_chars)
        word_list = wrapper.wrap(text=chunk)
        caption_new = '\n'.join(word_list)
        
        bbox = draw.textbbox((0, 0), caption_new, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        
        x_pos = (W - text_w) / 2
        y_pos = (H * 0.75) - (text_h / 2) 
        
        stroke_w = 4
        draw.text((x_pos, y_pos), caption_new, font=font, fill="#FFD700", align="center", stroke_width=stroke_w, stroke_fill="black")
        
        clip = ImageClip(np.array(img)).set_duration(duration_per_chunk)
        clips.append(clip)
        
    # DÜZELTME: concatenate_videoclips kullanıldı
    return concatenate_videoclips(clips)

# --- 5. DİĞER FONKSİYONLAR ---
async def generate_voice_over(text, output_file="voiceover.mp3"):
    communicate = edge_tts.Communicate(text, "en-US-ChristopherNeural")
    await communicate.save(output_file)

def get_stock_footage(query, duration):
    if not PEXELS_API_KEY: return None
    headers = {"Authorization": PEXELS_API_KEY}
    
    search_query = query
    if "horror" in query.lower(): search_query = "scary dark horror suspense"
    if "space" in query.lower(): search_query = "galaxy stars space universe"
    
    url = f"https://api.pexels.com/videos/search?query={search_query}&per_page=8&orientation=portrait"
    try:
        r = requests.get(url, headers=headers)
        data = r.json()
        video_files = []
        for video in data.get("videos", []):
            files = video.get("video_files", [])
            if files:
                good_files = [f for f in files if f["height"] > 700]
                if good_files:
                    video_files.append(random.choice(good_files)["link"])
                else:
                    video_files.append(files[0]["link"])
                    
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
        if not video_path: video_path = get_stock_footage("dark aesthetic", 10)
        if not video_path: return "Video bulunamadı."

        audio = AudioFileClip("voiceover.mp3")
        
        video_input = VideoFileClip(video_path)
        if video_input.duration < audio.duration:
            video = video_input.loop(duration=audio.duration)
        else:
            video = video_input.subclip(0, audio.duration)
        
        if video.h > 960: video = video.resize(height=960)
        w, h = video.size
        if w/h > 9/16:
            new_w = h * (9/16)
            video = video.crop(x1=(w/2 - new_w/2), width=new_w, height=h)
        
        video = video.set_audio(audio)
        
        try:
            subtitle_clip = create_dynamic_subtitles(script, video.duration, video.size)
            final_video = CompositeVideoClip([video, subtitle_clip])
        except Exception as e: 
            print(f"Altyazı hatası: {e}")
            final_video = video

        final_video.write_videofile("final_short.mp4", codec="libx264", audio_codec="aac", fps=24, preset='ultrafast', threads=1)
        
        video_input.close() 
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
    bot.reply_to(message, f"🎥 Konu: '{topic}'\n🧠 Gemini 2.5 hikayeyi yazıyor... (Bu işlem 1-2 dakika sürebilir)")
    
    script, warning = get_script(topic)
    
    result = create_video(topic, script)
    
    if result and "Hata" in result:
        bot.reply_to(message, f"❌ {result}")
    elif result:
        preview_text = script[:100] + "..."
        caption = f"🎬 **Konu:** {topic}\n📜 **Hikaye:** {preview_text}"
        if warning: caption += f"\n\n{warning}"
        
        with open(result, 'rb') as v:
            bot.send_video(message.chat.id, v, caption=caption)

bot.polling()
