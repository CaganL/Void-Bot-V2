import os
import telebot
import requests
import random
import json
import time
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import (
    VideoFileClip, AudioFileClip, ImageClip, CompositeVideoClip,
    concatenate_videoclips
)
import asyncio
import edge_tts

# --- AYARLAR ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# --- OTOMATİK HAYALET TEMİZLEYİCİ ---
def kill_webhook():
    if not TELEGRAM_TOKEN: return
    print("🧹 Webhook temizleniyor...")
    try:
        requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook?drop_pending_updates=True", timeout=5)
    except: pass

kill_webhook()

# Bot Kurulumu
bot = telebot.TeleBot(TELEGRAM_TOKEN, threaded=False)

# YouTube Shorts Boyutları (1080p Dikey)
W, H = 1080, 1920

# --- FONT İNDİRME ---
def get_font():
    font_path = "Oswald-Bold.ttf"
    if not os.path.exists(font_path):
        try:
            url = "https://github.com/google/fonts/raw/main/ofl/oswald/Oswald-Bold.ttf"
            with open(font_path, "wb") as f:
                f.write(requests.get(url, timeout=10).content)
        except: pass
    return font_path

# --- AI HİKAYE (KISA VE ÖZ) ---
def get_content(topic):
    # Video süresini kontrol altında tutmak için kelime sınırı
    models = ["gemini-2.5-flash", "gemini-2.0-flash-lite", "gemini-2.0-flash"]
    prompt = (
        f"Create a viral scary story about '{topic}'. "
        "Keep it VERY SHORT (Strictly under 90 words). "
        "The story must be fast-paced, engaging and end with a twist. "
        "Output ONLY JSON: {'script': 'story text', 'title': 'title', 'hashtags': '#tags'}"
    )
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    for model in models:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
            r = requests.post(url, json=payload, timeout=20)
            if r.status_code == 200:
                text = r.json()['candidates'][0]['content']['parts'][0]['text']
                return json.loads(text.replace("```json", "").replace("```", "").strip())
        except: continue

    return {
        "script": "I looked at the mirror. My reflection blinked. I didn't. Then it smiled.",
        "title": "The Mirror 😱",
        "hashtags": "#horror"
    }

# --- SES VE VİDEO İNDİRME ---
async def generate_resources(script):
    # Ses
    communicate = edge_tts.Communicate(script, "en-US-GuyNeural")
    await communicate.save("voice.mp3")
    audio = AudioFileClip("voice.mp3")
    
    # Video Arama
    headers = {"Authorization": PEXELS_API_KEY}
    queries = ["horror", "scary", "dark", "creepy", "nightmare", "suspense", "thriller"]
    random.shuffle(queries)
    paths = []
    current_dur = 0
    
    for q in queries:
        if current_dur >= audio.duration: break
        try:
            url = f"https://api.pexels.com/videos/search?query={q}&per_page=3&orientation=portrait"
            data = requests.get(url, headers=headers, timeout=10).json()
            for v in data.get("videos", []):
                if current_dur >= audio.duration: break
                files = v.get("video_files", [])
                if not files: continue
                
                # KALİTE AYARI:
                # En az 720p genişliği olanları al, en kalitelisini seç.
                suitable = [f for f in files if f["width"] >= 720]
                if not suitable: suitable = files
                
                link = sorted(suitable, key=lambda x: x["height"], reverse=True)[0]["link"]
                
                path = f"clip_{len(paths)}.mp4"
                with open(path, "wb") as f:
                    f.write(requests.get(link, timeout=15).content)
                
                try:
                    c = VideoFileClip(path)
                    if c.duration > 1:
                        paths.append(path)
                        current_dur += c.duration
                    c.close()
                except:
                    if os.path.exists(path): os.remove(path)
        except: continue
        
    return paths, audio

# --- AKILLI KIRPMA (Smart Crop) ---
def smart_resize(clip):
    target_ratio = W / H
    clip_ratio = clip.w / clip.h
    
    if clip_ratio > target_ratio:
        clip = clip.resize(height=H)
        clip = clip.crop(x1=clip.w/2 - W/2, width=W, height=H)
    else:
        clip = clip.resize(width=W)
        clip = clip.crop(y1=clip.h/2 - H/2, width=W, height=H)
        
    return clip

# --- MONTAJ VE ALTIN ORAN ÇIKTI ---
def build_video(content):
    try:
        paths, audio = asyncio.run(generate_resources(content["script"]))
        if not paths: return None
            
        clips = []
        for p in paths:
            try:
                c = VideoFileClip(p).without_audio()
                c = smart_resize(c)
                clips.append(c)
            except: continue

        if not clips: return None

        final_clip = concatenate_videoclips(clips, method="compose")
        final_clip = final_clip.set_audio(audio)
        
        if final_clip.duration > audio.duration:
            final_clip = final_clip.subclip(0, audio.duration)
        
        out = "final.mp4"
        
        # --- ALTIN ORAN AYARLARI ---
        # Preset: ultrafast (Donmayı engeller, işlemciyi rahatlatır)
        # Bitrate: 3500k (HD Kalite ama Telegram sınırını aşmaz)
        final_clip.write_videofile(
            out, 
            fps=24, 
            codec="libx264", 
            preset="ultrafast",  # <-- HIZ İÇİN BUNU DEĞİŞTİRDİK
            bitrate="3500k",     # <-- GÜVENLİ VE KALİTELİ ARALIK
            audio_bitrate="192k",
            threads=4, 
            logger=None
        )
        
        # Temizlik
        audio.close()
        for c in clips: c.close()
        for p in paths: 
            if os.path.exists(p): os.remove(p)
            
        return out
    except Exception as e:
        print(f"Hata: {e}")
        return None

# --- TELEGRAM ---
@bot.message_handler(commands=["video"])
def handle_video(message):
    try:
        bot.reply_to(message, "🎬 Video hazırlanıyor... (HD Kalite, Hızlı Mod)")
        args = message.text.split(maxsplit=1)
        topic = args[1] if len(args) > 1 else "scary story"
        
        content = get_content(topic)
        path = build_video(content)
        
        if path and os.path.exists(path):
            with open(path, "rb") as v:
                bot.send_video(message.chat.id, v, caption=f"🎥 **{content['title']}**\n{content['hashtags']}")
        else:
            bot.reply_to(message, "❌ Video oluşturulamadı.")
            
    except Exception as e:
        bot.reply_to(message, f"Hata: {e}")

print("🤖 Bot Aktif!")
bot.polling(non_stop=True)

