import os
import telebot
import requests
import random
import asyncio
import edge_tts
import numpy as np
import textwrap
from PIL import Image, ImageDraw, ImageFont 
# DÜZELTME: Doğru import biçimi budur
from moviepy.editor import VideoFileClip, AudioFileClip, ImageClip, CompositeVideoClip, concatenate_videoclips

# --- AYARLAR ---
# DİKKAT: Buraya tokeni yapıştırırken tırnak içinde BOŞLUKSUZ yaz!
TELEGRAM_TOKEN = "8395962603:AAFmuGIsQ2DiUD8nV7ysUjkGbsr1dmGlqKo"
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

bot = telebot.TeleBot(TELEGRAM_TOKEN)

# --- YAMA ---
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

# --- SENARYO ---
def get_script(topic):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    prompt = f"Write a terrifying horror story about '{topic}' for a YouTube Short. Approx 115 words. Simple English."
    try:
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        response = requests.post(url, json=payload, timeout=10)
        return response.json()['candidates'][0]['content']['parts'][0]['text'].strip()
    except:
        return "You think you are alone in your room. But look at your window. Did you see that shadow move? It's waiting for you to look away."

# --- MONTAJ ---
def create_video(topic, script):
    try:
        asyncio.run(edge_tts.Communicate(script, "en-US-ChristopherNeural").save("voiceover.mp3"))
        audio = AudioFileClip("voiceover.mp3")
        
        # Pexels araması
        headers = {"Authorization": PEXELS_API_KEY}
        r = requests.get(f"https://api.pexels.com/videos/search?query={topic}&per_page=5&orientation=portrait", headers=headers)
        videos = r.json().get("videos", [])
        if not videos: return "Video yok."
        
        path = "input.mp4"
        with open(path, "wb") as f: f.write(requests.get(videos[0]["video_files"][0]["link"]).content)
        
        video = VideoFileClip(path)
        if video.duration < audio.duration:
            video = video.loop(duration=audio.duration)
        else:
            video = video.subclip(0, audio.duration)
        
        video = video.resize(height=960).set_audio(audio)
        
        # Altyazı Tasarımı
        font_p = download_font()
        img = Image.new('RGBA', (video.w, video.h), (0,0,0,0))
        draw = ImageDraw.Draw(img)
        font = ImageFont.truetype(font_p, int(video.w/12))
        
        wrapper = textwrap.TextWrapper(width=20)
        caption = "\n".join(wrapper.wrap(text=script[:50] + "...")) # Özet altyazı
        
        draw.text((video.w/2, video.h*0.7), caption, font=font, fill="#FFD700", anchor="mm", stroke_width=4, stroke_fill="black")
        sub_clip = ImageClip(np.array(img)).set_duration(video.duration)
        
        final = CompositeVideoClip([video, sub_clip])
        final.write_videofile("output.mp4", codec="libx264", audio_codec="aac", fps=24, preset='ultrafast', threads=1)
        
        video.close()
        audio.close()
        return "output.mp4"
    except Exception as e: return str(e)

@bot.message_handler(commands=['video'])
def handle(message):
    topic = message.text.split(maxsplit=1)[1] if len(message.text.split()) > 1 else "scary"
    bot.reply_to(message, "🎬 Railway canlanıyor, video hazırlanıyor...")
    script = get_script(topic)
    res = create_video(topic, script)
    if "output" in res:
        with open(res, 'rb') as v: bot.send_video(message.chat.id, v)
    else: bot.reply_to(message, f"Hata: {res}")

bot.polling()
