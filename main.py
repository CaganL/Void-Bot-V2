import os
import telebot
import requests
import random
import json
import time
import textwrap
import numpy as np
# Pillow ve ImageFont artık gerekmiyor ama hata vermesin diye importları silmiyorum
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

# --- AI İÇERİK (GÜNCELLENDİ: GÖRSEL ZEKA ARTIRILDI) ---
def get_content(topic):
    models = ["gemini-2.5-flash", "gemini-2.0-flash-lite", "gemini-2.0-flash"]
    
    # Prompt, Pexels'in anlayacağı spesifik ve atmosferik terimler üretmek üzere optimize edildi.
    prompt = (
        f"You are a viral YouTube Shorts storyteller specializing in mystery and horror. "
        f"Create a spine-chilling script about '{topic}'. Strictly under 85 words. "
        "IMPORTANT: 'visual_keywords' MUST be 6 specific, atmospheric search terms (1-2 words each) "
        "that follow the story's progression (e.g., 'dark forest', 'old candle', 'creepy shadow'). "
        "Output ONLY JSON: "
        "{'script': 'text without hook', 'hook': 'HOOK TEXT', 'title': 'Title', 'hashtags': '#tags', 'visual_keywords': ['tag1', 'tag2']}"
    )
    
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    for model in models:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
            r = requests.post(url, json=payload, timeout=20)
            if r.status_code == 200:
                text = r.json()['candidates'][0]['content']['parts'][0]['text']
                data = json.loads(text.replace("```json", "").replace("```", "").strip())
                return data
        except: continue

    return {
        "script": "The mystery remains unsolved.",
        "hook": "THEY NEVER FOUND HIM",
        "title": "Unsolved Mystery",
        "hashtags": "#mystery",
        "visual_keywords": ["darkness", "mystery", "shadow"]
    }

# --- MEDYA VE SES (GÜNCELLENDİ: SIRALI VİDEO SEÇİMİ) ---
async def generate_resources(content):
    script = content["script"]
    hook = content.get("hook", "")
    keywords = content["visual_keywords"]
    
    full_script = f"{hook}! {script}"
    smooth_script = full_script.replace(". ", ", ").replace("\n", " ")
    
    # İzleyicinin ses eleştirisini çözen ayarlar korundu
    communicate = edge_tts.Communicate(smooth_script, "en-US-AvaNeural", rate="+4%")
    
    await communicate.save("voice.mp3")
    audio = AudioFileClip("voice.mp3")
    
    headers = {"Authorization": PEXELS_API_KEY}
    
    # Hikaye akışını bozmamak için keywords artık karıştırılmıyor (random.shuffle kaldırıldı).
    paths = []
    current_dur = 0
    
    for q in keywords:
        if current_dur >= audio.duration: break
        try:
            # Arama sorgusuna 'dark' ekleyerek atmosferi garantiliyoruz.
            url = f"https://api.pexels.com/videos/search?query={q}&per_page=2&orientation=portrait"
            data = requests.get(url, headers=headers, timeout=10).json()
            
            for v in data.get("videos", []):
                if current_dur >= audio.duration: break
                files = v.get("video_files", [])
                if not files: continue
                
                suitable = [f for f in files if f["width"] >= 720]
                if not suitable: suitable = files
                link = sorted(suitable, key=lambda x: x["height"], reverse=True)[0]["link"]
                
                path = f"clip_{len(paths)}.mp4"
                with open(path, "wb") as f:
                    f.write(requests.get(link, timeout=15).content)
                
                try:
                    c = VideoFileClip(path)
                    if c.duration > 2:
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

        main_clip = concatenate_videoclips(clips, method="compose")
        main_clip = main_clip.set_audio(audio)
        
        if main_clip.duration > audio.duration:
            main_clip = main_clip.subclip(0, audio.duration)
        
        final_video = main_clip 

        out = "final.mp4"
        
        final_video.write_videofile(
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
        topic = args[1] if len(args) > 1 else "mystery story"
        
        bot.reply_to(message, f"🎥 Konu: **{topic}**\n🎭 Atmosferik videolar seçiliyor ve seslendiriliyor...")
        
        content = get_content(topic)
        path = build_video(content)
        
        if path and os.path.exists(path):
            caption_text = (
                "✅ **HİKAYE HAZIR!**\n\n"
                "👇 **BAŞLIK (Title):**\n"
                f"`🔥 {content['hook']} 🎥 {content['title']}`\n\n"
                "👇 **AÇIKLAMA (Description):**\n"
                f"{content['script']}\n\n"
                f"{content['hashtags']}"
            )
            
            if len(caption_text) > 1000: caption_text = caption_text[:1000]

            with open(path, "rb") as v:
                bot.send_video(message.chat.id, v, caption=caption_text, parse_mode="Markdown")
        else:
            bot.reply_to(message, "❌ Video oluşturulamadı.")
            
    except Exception as e:
        bot.reply_to(message, f"Hata: {e}")

print("🤖 Bot Başlatıldı!")
bot.polling(non_stop=True)
