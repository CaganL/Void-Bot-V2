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

# --- AYARLAR (GÜVENLİ MOD) ---
# GitHub kızmasın diye şifreyi buradan değil, Railway'den alıyoruz:
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# --- OTOMATİK HAYALET TEMİZLEYİCİ ---
# Bu fonksiyon, bot her açıldığında eski "Conflict" yaratan bağlantıları siler.
def kill_webhook():
    if not TELEGRAM_TOKEN:
        print("⚠️ Token bulunamadı! Lütfen Railway Variables kısmını kontrol et.")
        return
        
    print("🧹 Hayalet bağlantılar (Webhook) temizleniyor...")
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook?drop_pending_updates=True"
    try:
        r = requests.get(url, timeout=10)
        print(f"Webhook Temizleme Sonucu: {r.text}")
    except Exception as e:
        print(f"⚠️ Temizleme sırasında hata (Önemli değil): {e}")

# Botu başlatmadan önce temizlik yap
kill_webhook()

# Bot Kurulumu
bot = telebot.TeleBot(TELEGRAM_TOKEN, threaded=False)

# YouTube Shorts Boyutları
W, H = 1080, 1920

# --- FONT İNDİRME ---
def get_font():
    font_path = "Oswald-Bold.ttf"
    if not os.path.exists(font_path):
        url = "https://github.com/google/fonts/raw/main/ofl/oswald/Oswald-Bold.ttf"
        try:
            r = requests.get(url, timeout=10)
            with open(font_path, "wb") as f:
                f.write(r.content)
        except:
            pass
    return font_path

# --- AI HİKAYE OLUŞTURUCU ---
def get_content(topic):
    # Senin loglarında en başarılı çalışan model listesi
    models_to_try = ["gemini-2.5-flash", "gemini-2.0-flash-lite", "gemini-2.0-flash"]

    prompt = (
        f"You are a professional YouTube Shorts creator. Create a viral scary story about '{topic}'. "
        "Output ONLY a valid JSON object with the following keys:\n"
        "- 'script': The scary story text (Minimum 100 words, simple English).\n"
        "- 'title': A clickbait title.\n"
        "- 'description': Short description.\n"
        "- 'hashtags': Popular hashtags.\n"
        "Do not write anything else, just the JSON."
    )
    
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    for model in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
        print(f"🔄 Model deneniyor: {model}...")

        try:
            r = requests.post(url, json=payload, timeout=25)
            if r.status_code == 200:
                try:
                    raw_text = r.json()['candidates'][0]['content']['parts'][0]['text']
                    raw_text = raw_text.replace("```json", "").replace("```", "").strip()
                    return json.loads(raw_text)
                except:
                    continue
            elif r.status_code == 429:
                print(f"⚠️ Kota dolu ({model}), geçiliyor...")
                continue
        except:
            continue

    # Hiçbiri çalışmazsa yedek hikaye
    return {
        "script": "I looked at the mirror. My reflection blinked. I didn't. Then it smiled.",
        "title": "The Mirror Glitch 😱",
        "description": "Scary story.",
        "hashtags": "#horror"
    }

# --- SES VE VİDEO ---
async def generate_tts_and_get_videos(script):
    print("🔊 Ses oluşturuluyor...")
    communicate = edge_tts.Communicate(script, "en-US-GuyNeural")
    await communicate.save("voice.mp3")
    
    audio = AudioFileClip("voice.mp3")
    print(f"⏱️ Ses süresi: {audio.duration} sn.")

    headers = {"Authorization": PEXELS_API_KEY}
    queries = ["horror", "scary", "dark", "shadow", "fear"]
    random.shuffle(queries)
    paths = []
    current = 0
    i = 0
    
    for q in queries:
        if current >= audio.duration: break
        # Pexels'den dikey video ara
        url = f"https://api.pexels.com/videos/search?query={q}&per_page=3&orientation=portrait"
        try:
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code != 200: continue
            data = r.json().get("videos", [])
            
            for v in data:
                if current >= audio.duration: break
                files = v.get("video_files", [])
                if not files: continue
                # En iyi kaliteyi değil, en uyumlu olanı seç (Hızlı indirilsin)
                link = sorted(files, key=lambda x: x["height"], reverse=True)[0]["link"]
                
                path = f"clip_{i}.mp4"
                with open(path, "wb") as f:
                    f.write(requests.get(link, timeout=15).content)
                
                clip = VideoFileClip(path)
                if clip.duration > 1:
                    paths.append(path)
                    current += clip.duration
                    i += 1
                clip.close()
        except:
            continue
    return paths, audio

# --- MONTAJ ---
def build_video(content):
    try:
        paths, audio = asyncio.run(generate_tts_and_get_videos(content["script"]))
        if not paths: return None
            
        print("🎬 Montaj başlıyor...")
        clips = []
        for p in paths:
            c = VideoFileClip(p).without_audio().resize(height=H)
            c = c.crop(x1=c.w/2 - W/2, width=W, height=H)
            clips.append(c)

        main = concatenate_videoclips(clips, method="compose")
        main = main.set_audio(audio)
        if main.duration > audio.duration:
            main = main.subclip(0, audio.duration)
        
        out = "final.mp4"
        main.write_videofile(out, fps=24, preset="ultrafast", threads=4, logger=None)
        
        audio.close()
        for c in clips: c.close()
        return out
    except Exception as e:
        print(f"Montaj Hatası: {e}")
        return None

# --- TELEGRAM ---
@bot.message_handler(commands=["video"])
def handle_video(message):
    try:
        bot.reply_to(message, "⏳ Video hazırlanıyor... (Yaklaşık 1 dakika)")
        
        args = message.text.split(maxsplit=1)
        topic = args[1] if len(args) > 1 else "scary story"
        
        content = get_content(topic)
        path = build_video(content)
        
        if path and os.path.exists(path):
            cap = f"🎥 **{content['title']}**\n\n{content['hashtags']}"
            with open(path, "rb") as v:
                bot.send_video(message.chat.id, v, caption=cap, parse_mode="Markdown")
        else:
            bot.reply_to(message, "❌ Video oluşturulamadı.")
            
    except Exception as e:
        print(f"Hata: {e}")
        bot.reply_to(message, "Bir hata oluştu.")

# Botu Sürekli Çalıştır
print("🤖 Bot başlatılıyor...")
bot.polling(non_stop=True)

