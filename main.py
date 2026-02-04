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

# --- TEMİZLİK ---
def kill_webhook():
    if not TELEGRAM_TOKEN: return
    try:
        requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook?drop_pending_updates=True", timeout=5)
    except: pass

kill_webhook()

bot = telebot.TeleBot(TELEGRAM_TOKEN, threaded=False)
W, H = 1080, 1920

# --- FONT ---
def get_font():
    font_path = "Oswald-Bold.ttf"
    if not os.path.exists(font_path):
        try:
            url = "https://github.com/google/fonts/raw/main/ofl/oswald/Oswald-Bold.ttf"
            with open(font_path, "wb") as f:
                f.write(requests.get(url, timeout=10).content)
        except: pass
    return font_path

# --- AI HİKAYE VE GÖRSEL PLANLAMA ---
def get_content(topic):
    models = ["gemini-2.5-flash", "gemini-2.0-flash-lite", "gemini-2.0-flash"]
    
    # ARTIK KORKU DEĞİL, KONUYA GÖRE DAVRANACAK:
    prompt = (
        f"You are a viral content creator. Create a short, engaging video script about '{topic}'. "
        "Strictly under 100 words. "
        "1. If the topic is 'motivation', be inspiring and powerful. "
        "2. If the topic is 'horror', be scary. "
        "3. If the topic is 'facts', be informative. "
        "Also provide 5 English search keywords for stock footage related to this script. "
        "Output ONLY JSON: "
        "{'script': 'the text spoken', 'title': 'Clickbait Title', 'hashtags': '#tags', 'visual_keywords': ['tag1', 'tag2', 'tag3']}"
    )
    
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    for model in models:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
            r = requests.post(url, json=payload, timeout=20)
            if r.status_code == 200:
                text = r.json()['candidates'][0]['content']['parts'][0]['text']
                data = json.loads(text.replace("```json", "").replace("```", "").strip())
                # Eğer görsel kelimeleri gelmezse konuyu kullan
                if "visual_keywords" not in data: 
                    data["visual_keywords"] = [topic, "cinematic", "atmosphere"]
                return data
        except: continue

    # Yedek Plan
    return {
        "script": "Success is not final, failure is not fatal: it is the courage to continue that counts.",
        "title": "Never Give Up 💪",
        "hashtags": "#motivation #success",
        "visual_keywords": ["success", "man running", "sunshine", "gym", "focus"]
    }

# --- MEDYA İNDİRME ---
async def generate_resources(content):
    script = content["script"]
    keywords = content["visual_keywords"] # Artık Gemini'nin önerdiği kelimeleri kullanıyoruz
    
    # Ses (Konuya göre ses tonu değişmez ama standart erkek sesi iyidir)
    communicate = edge_tts.Communicate(script, "en-US-GuyNeural")
    await communicate.save("voice.mp3")
    audio = AudioFileClip("voice.mp3")
    
    headers = {"Authorization": PEXELS_API_KEY}
    random.shuffle(keywords) # Kelimeleri karıştır
    paths = []
    current_dur = 0
    
    print(f"🔍 Aranan Kelimeler: {keywords}")

    for q in keywords:
        if current_dur >= audio.duration: break
        try:
            # Dikey video ara
            url = f"https://api.pexels.com/videos/search?query={q}&per_page=3&orientation=portrait"
            data = requests.get(url, headers=headers, timeout=10).json()
            
            for v in data.get("videos", []):
                if current_dur >= audio.duration: break
                files = v.get("video_files", [])
                if not files: continue
                
                # Kalite Filtresi (En az 720p)
                suitable = [f for f in files if f["width"] >= 720]
                if not suitable: suitable = files
                link = sorted(suitable, key=lambda x: x["height"], reverse=True)[0]["link"]
                
                path = f"clip_{len(paths)}.mp4"
                with open(path, "wb") as f:
                    f.write(requests.get(link, timeout=15).content)
                
                try:
                    c = VideoFileClip(path)
                    if c.duration > 2: # Çok kısa videoları alma
                        paths.append(path)
                        current_dur += c.duration
                    c.close()
                except:
                    if os.path.exists(path): os.remove(path)
        except: continue
        
    return paths, audio

# --- AKILLI KIRPMA ---
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

# --- MONTAJ ---
def build_video(content):
    try:
        paths, audio = asyncio.run(generate_resources(content))
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
        
        # ALTIN ORAN: Hızlı Render + Yüksek Kalite
        final_clip.write_videofile(
            out, fps=24, codec="libx264", preset="ultrafast", 
            bitrate="3500k", audio_bitrate="192k", threads=4, logger=None
        )
        
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
        args = message.text.split(maxsplit=1)
        topic = args[1] if len(args) > 1 else "motivation"
        
        bot.reply_to(message, f"🎥 Konu: **{topic}**\nSenaryo yazılıyor ve uygun stok videolar aranıyor...")
        
        content = get_content(topic)
        path = build_video(content)
        
        if path and os.path.exists(path):
            # AÇIKLAMA KISMINA METNİ EKLİYORUZ:
            caption_text = (
                f"🎥 **{content['title']}**\n\n"
                f"📝 _Script:_\n{content['script']}\n\n"
                f"{content['hashtags']}"
            )
            
            # Telegram caption sınırı 1024 karakterdir, kesilmesin diye kontrol:
            if len(caption_text) > 1000:
                caption_text = caption_text[:1000] + "..."

            with open(path, "rb") as v:
                bot.send_video(message.chat.id, v, caption=caption_text, parse_mode="Markdown")
        else:
            bot.reply_to(message, "❌ Video oluşturulamadı.")
            
    except Exception as e:
        bot.reply_to(message, f"Hata: {e}")

print("🤖 Bot Başlatıldı!")
bot.polling(non_stop=True)
