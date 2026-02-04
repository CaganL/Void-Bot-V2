import os
import telebot
import requests
import random
import json
import time
import numpy as np
import textwrap
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

# Botu başlat (Threaded=False hata takibi için daha iyidir)
bot = telebot.TeleBot(TELEGRAM_TOKEN, threaded=False)

W, H = 1080, 1920
FPS = 30

def get_font():
    font_path = "Oswald-Bold.ttf"
    if not os.path.exists(font_path):
        url = "https://github.com/google/fonts/raw/main/ofl/oswald/Oswald-Bold.ttf"
        try:
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                with open(font_path, "wb") as f:
                    f.write(r.content)
        except:
            pass
    return font_path

# --- 1. ADIM: HİKAYE YAZILIMI ---
def get_content(topic):
    # Senin başarı aldığın liste (Önce Lite, sonra güçlüler)
    models_to_try = [
        "gemini-2.0-flash-lite", 
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-exp-1206"
    ]

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
                print(f"✅ BAŞARILI: {model}")
                try:
                    raw_text = r.json()['candidates'][0]['content']['parts'][0]['text']
                    raw_text = raw_text.replace("```json", "").replace("```", "").strip()
                    return json.loads(raw_text)
                except:
                    print(f"⚠️ JSON Hatası ({model}), diğerine geçiliyor.")
                    continue
            
            elif r.status_code == 429:
                print(f"⚠️ KOTA DOLU ({model}). Hızlıca diğerine geçiliyor...")
                continue
            
            else:
                print(f"❌ API HATA ({model}): {r.status_code}")
                continue
                
        except Exception as e:
            print(f"Bağlantı sorunu ({model}): {e}")
            continue

    # YEDEK SENARYO
    print("🚨 TÜM MODELLER BAŞARISIZ! Yedek senaryo devreye giriyor.")
    return {
        "script": "I woke up. The house was silent. I reached for my phone. It wasn't there. Then I heard a sound breathing under my bed. I looked down. Red eyes were staring back.",
        "title": "Nightmare 🌑",
        "description": "Scary story.",
        "hashtags": "#horror #shorts"
    }

# --- 2. ADIM: TTS VE VİDEO İNDİRME ---
async def generate_tts_and_get_videos(script):
    print("🔊 Ses oluşturuluyor (TTS)...")
    communicate = edge_tts.Communicate(script, "en-US-GuyNeural")
    await communicate.save("voice.mp3")
    
    audio = AudioFileClip("voice.mp3")
    duration = audio.duration
    print(f"⏱️ Ses süresi: {duration} saniye. Videolar aranıyor...")

    headers = {"Authorization": PEXELS_API_KEY}
    queries = ["horror", "scary", "dark", "shadow", "night"]
    random.shuffle(queries)
    paths = []
    current = 0
    i = 0
    
    for q in queries:
        if current >= duration: break
        print(f"🔎 Pexels'de aranıyor: {q}")
        url = f"https://api.pexels.com/videos/search?query={q}&per_page=3&orientation=portrait"
        try:
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code != 200: continue
            data = r.json().get("videos", [])
            
            for v in data:
                if current >= duration: break
                files = v.get("video_files", [])
                if not files: continue
                # SD kalite (Hızlı indirme için)
                link = sorted(files, key=lambda x: x["height"], reverse=True)[0]["link"]
                
                path = f"clip_{i}.mp4"
                print(f"⬇️ Video indiriliyor: {path}")
                with open(path, "wb") as f:
                    f.write(requests.get(link, timeout=15).content)
                
                clip = VideoFileClip(path)
                if clip.duration > 1:
                    paths.append(path)
                    current += clip.duration
                    i += 1
                clip.close()
        except Exception as e:
            print(f"Video hatası: {e}")
            continue
            
    return paths, audio

# --- 3. ADIM: MONTAJ ---
def make_subtitles(text, duration):
    font_path = get_font()
    try: font = ImageFont.truetype(font_path, 55)
    except: font = ImageFont.load_default()
    
    words = text.split()
    chunks = [" ".join(words[i:i+3]) for i in range(0, len(words), 3)]
    if not chunks: return None
    
    per = duration / len(chunks)
    clips = []
    
    for ch in chunks:
        img = Image.new("RGBA", (W, H), (0,0,0,0))
        draw = ImageDraw.Draw(img)
        w_text = draw.textlength(ch, font=font)
        x = (W - w_text) // 2
        y = int(H * 0.75)
        draw.rectangle([x-20, y-10, x+w_text+20, y+70], fill=(0,0,0,140))
        draw.text((x, y), ch, font=font, fill="white")
        clips.append(ImageClip(np.array(img)).set_duration(per))
        
    return concatenate_videoclips(clips, method="compose")

def build_video(content):
    try:
        paths, audio = asyncio.run(generate_tts_and_get_videos(content["script"]))
        
        if not paths:
            print("❌ HATA: Hiç video indirilemedi!")
            return None
            
        print(f"🎬 {len(paths)} klip birleştiriliyor...")
        clips = []
        for p in paths:
            # Bellek dostu resize işlemi
            c = VideoFileClip(p).without_audio().resize(height=H)
            c = c.crop(x1=c.w/2 - W/2, width=W, height=H)
            clips.append(c)

        main = concatenate_videoclips(clips, method="compose")
        main = main.set_audio(audio)
        if main.duration > audio.duration:
            main = main.subclip(0, audio.duration)
            
        print("📝 Altyazılar ekleniyor...")
        subs = make_subtitles(content["script"], main.duration)
        final = CompositeVideoClip([main, subs], size=(W,H)) if subs else main
        
        out = "final.mp4"
        print("💾 Video render alınıyor (Bu biraz sürebilir)...")
        # Preset ultrafast ile hızlı render
        final.write_videofile(out, fps=24, preset="ultrafast", threads=4, logger=None)
        
        audio.close()
        for c in clips: c.close()
        for p in paths: 
            if os.path.exists(p): os.remove(p)
            
        return out
    except Exception as e:
        print(f"❌ MONTAJ HATASI: {e}")
        return None

# --- TELEGRAM ---
@bot.message_handler(commands=["video"])
def handle_video(message):
    try:
        args = message.text.split(maxsplit=1)
        topic = args[1] if len(args) > 1 else "scary story"
        
        bot.reply_to(message, "⏳ Video hazırlanıyor... Logları takip et.")
        
        print(f"🚀 Yeni İstek: {topic}")
        content = get_content(topic)
        path = build_video(content)
        
        if path and os.path.exists(path):
            print("📤 Video Telegram'a yükleniyor...")
            cap = f"🎥 **{content['title']}**\n\n{content['hashtags']}"
            with open(path, "rb") as v:
                bot.send_video(message.chat.id, v, caption=cap, parse_mode="Markdown")
            print("✅ İŞLEM TAMAMLANDI!")
        else:
            bot.reply_to(message, "❌ Video oluşturulamadı. Loglara bak.")
            
    except Exception as e:
        print(f"Genel Hata: {e}")
        bot.reply_to(message, f"Hata: {e}")

# Sonsuz döngü (Çökse bile kalkar)
while True:
    try:
        print("🤖 Bot başlatılıyor...")
        bot.polling(non_stop=True, interval=2)
    except Exception as e:
        print(f"⚠️ Bot çöktü (Muhtemelen 409 Conflict): {e}")
        print("♻️ 5 saniye içinde yeniden başlatılıyor...")
        time.sleep(5)

