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

# YouTube Shorts Boyutları
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

# --- AI HİKAYE ---
def get_content(topic):
    models = ["gemini-2.5-flash", "gemini-2.0-flash-lite", "gemini-2.0-flash"]
    prompt = (
        f"Create a viral scary story about '{topic}'. "
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
        "script": "I heard a knock on the mirror. It came from inside.",
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
    queries = ["horror", "scary", "dark", "creepy", "nightmare"]
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
                # En yüksek kaliteyi değil, HD olanı seç (Hız ve boyut için)
                best = sorted(files, key=lambda x: x["height"], reverse=True)[0]["link"]
                
                path = f"clip_{len(paths)}.mp4"
                with open(path, "wb") as f:
                    f.write(requests.get(best, timeout=15).content)
                
                # İnen dosya sağlam mı kontrol et
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

# --- AKILLI KIRPMA FONKSİYONU (YENİ) ---
# Videoyu çubuk gibi yapmadan ekrana tam oturtur
def smart_resize(clip):
    target_ratio = W / H
    clip_ratio = clip.w / clip.h
    
    if clip_ratio > target_ratio:
        # Video genişse: Yüksekliğe göre ayarla, kenarları kırp
        clip = clip.resize(height=H)
        clip = clip.crop(x1=clip.w/2 - W/2, width=W, height=H)
    else:
        # Video inceyse: Genişliğe göre ayarla, altı/üstü kırp (ÇUBUK SORUNU ÇÖZÜMÜ)
        clip = clip.resize(width=W)
        clip = clip.crop(y1=clip.h/2 - H/2, width=W, height=H)
        
    return clip

# --- MONTAJ ---
def build_video(content):
    try:
        paths, audio = asyncio.run(generate_resources(content["script"]))
        if not paths: return None
            
        clips = []
        for p in paths:
            try:
                c = VideoFileClip(p).without_audio()
                # Yeni akıllı boyutlandırmayı kullan
                c = smart_resize(c)
                clips.append(c)
            except: continue

        if not clips: return None

        final_clip = concatenate_videoclips(clips, method="compose")
        final_clip = final_clip.set_audio(audio)
        
        # Süreyi eşitle
        if final_clip.duration > audio.duration:
            final_clip = final_clip.subclip(0, audio.duration)
        
        out = "final.mp4"
        final_clip.write_videofile(out, fps=24, preset="ultrafast", threads=4, logger=None)
        
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
        bot.reply_to(message, "🎬 Video hazırlanıyor... (Görüntü tam ekran yapılıyor)")
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

