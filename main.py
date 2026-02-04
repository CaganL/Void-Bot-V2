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

# Botu başlatırken threaded=False yapıyoruz ki hata olursa görelim ama çökmesin
bot = telebot.TeleBot(TELEGRAM_TOKEN, threaded=False)

W, H = 1080, 1920
FPS = 30

# --- FONT ---
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

# --- TTS ---
async def generate_tts(text, out="voice.mp3", voice="en-US-GuyNeural"):
    communicate = edge_tts.Communicate(text, voice)
    try:
        if os.path.exists(out): os.remove(out)
        await communicate.save(out)
    except Exception as e:
        print(f"TTS Hatası: {e}")

# --- İÇERİK ÜRETİCİ ---
def get_content(topic):
    # Senin modellerin
    models_to_try = [
        "gemini-2.0-flash-lite", 
        "gemini-2.0-flash",
        "gemini-2.5-flash",
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
                    continue # JSON bozuksa diğer modele geç
            
            elif r.status_code == 429:
                print(f"⚠️ KOTA DOLU ({model}). Hızlıca diğerine geçiliyor...")
                continue # Beklemeden diğer modele geç
            
            else:
                print(f"❌ HATA ({model}): {r.status_code}")
                continue
                
        except Exception as e:
            print(f"Bağlantı sorunu ({model}): {e}")
            continue

    # --- GARANTİ YEDEK ---
    # Eğer yukarıdakilerin hepsi başarısız olursa bu çalışacak
    print("🚨 TÜM MODELLER BAŞARISIZ! Yedek senaryo devreye giriyor.")
    return {
        "script": "I woke up in the middle of the night. The house was silent. Too silent. I reached for my phone to check the time, but it wasn't there. Then I heard a sound breathing under my bed. I slowly looked down. Two red eyes were staring back at me. They whispered my name. I tried to scream, but no sound came out. That is when I realized, I was not in my room anymore.",
        "title": "Nightmare Reality 🌑",
        "description": "When your safe place becomes your worst nightmare.",
        "hashtags": "#horror #scary #creepy #shorts"
    }

# --- VİDEO İŞLEMLERİ (Basitleştirilmiş) ---
def get_videos(total_duration):
    headers = {"Authorization": PEXELS_API_KEY}
    queries = ["horror", "scary", "dark", "shadow", "night"]
    random.shuffle(queries)
    paths = []
    current = 0
    i = 0
    
    for q in queries:
        if current >= total_duration: break
        url = f"https://api.pexels.com/videos/search?query={q}&per_page=3&orientation=portrait"
        try:
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code != 200: continue
            data = r.json().get("videos", [])
            
            for v in data:
                if current >= total_duration: break
                files = v.get("video_files", [])
                if not files: continue
                # En düşük kaliteyi değil, ortalama bir kaliteyi alalım ki işlem hızlı olsun
                link = sorted(files, key=lambda x: x["height"], reverse=True)[0]["link"]
                
                path = f"clip_{i}.mp4"
                with open(path, "wb") as f:
                    f.write(requests.get(link, timeout=15).content)
                
                # Kontrol et
                clip = VideoFileClip(path)
                if clip.duration > 1:
                    paths.append(path)
                    current += clip.duration
                    i += 1
                clip.close()
        except:
            continue
    return paths

def make_subtitles(text, duration):
    font_path = get_font()
    try: font = ImageFont.truetype(font_path, 55)
    except: font = ImageFont.load_default()
    
    words = text.split()
    # Kelimeleri 3'erli grupla (daha hızlı okuma)
    chunks = [" ".join(words[i:i+3]) for i in range(0, len(words), 3)]
    if not chunks: return None
    
    per = duration / len(chunks)
    clips = []
    
    for ch in chunks:
        img = Image.new("RGBA", (W, H), (0,0,0,0))
        draw = ImageDraw.Draw(img)
        
        # Basit ortalama
        w_text = draw.textlength(ch, font=font)
        x = (W - w_text) // 2
        y = int(H * 0.75)
        
        draw.rectangle([x-20, y-10, x+w_text+20, y+70], fill=(0,0,0,140))
        draw.text((x, y), ch, font=font, fill="white")
        
        clips.append(ImageClip(np.array(img)).set_duration(per))
        
    return concatenate_videoclips(clips, method="compose")

def build_video(content):
    try:
        script = content["script"]
        asyncio.run(generate_tts(script, "voice.mp3"))
        
        audio = AudioFileClip("voice.mp3")
        paths = get_videos(audio.duration)
        
        if not paths:
            print("Video bulunamadı!")
            return None
            
        clips = [VideoFileClip(p).without_audio().resize(height=H).crop(x1=0, y1=0, width=W, height=H) for p in paths]
        
        # Boyut hatası almamak için her klibi zorla 1080x1920 yap
        final_clips = []
        for c in clips:
            c = c.resize(newsize=(W, H)) 
            final_clips.append(c)

        main = concatenate_videoclips(final_clips, method="compose")
        main = main.set_audio(audio)
        if main.duration > audio.duration:
            main = main.subclip(0, audio.duration)
            
        subs = make_subtitles(script, main.duration)
        final = CompositeVideoClip([main, subs], size=(W,H)) if subs else main
        
        out = "final.mp4"
        final.write_videofile(out, fps=24, preset="ultrafast", threads=4) # Hız için optimize
        
        # Temizlik
        audio.close()
        for c in final_clips: c.close()
        for p in paths: 
            if os.path.exists(p): os.remove(p)
            
        return out
    except Exception as e:
        print(f"Montaj hatası: {e}")
        return None

# --- TELEGRAM ---
@bot.message_handler(commands=["video"])
def handle_video(message):
    try:
        args = message.text.split(maxsplit=1)
        topic = args[1] if len(args) > 1 else "scary story"
        
        bot.reply_to(message, "⏳ Video hazırlanıyor... (API hataları olsa bile yedek devreye girecek)")
        
        content = get_content(topic)
        path = build_video(content)
        
        if path and os.path.exists(path):
            cap = f"🎥 **{content['title']}**\n\n{content['hashtags']}"
            with open(path, "rb") as v:
                bot.send_video(message.chat.id, v, caption=cap, parse_mode="Markdown")
        else:
            bot.reply_to(message, "❌ Video oluşturulamadı.")
            
    except Exception as e:
        bot.reply_to(message, f"Beklenmedik hata: {e}")

# Botu sürekli yeniden başlatma modunda çalıştırıyoruz (Auto-Restart)
while True:
    try:
        print("Bot başlatılıyor...")
        bot.polling(non_stop=True, interval=2)
    except Exception as e:
        print(f"Bot çöktü, 5 saniye sonra yeniden başlıyor: {e}")
        time.sleep(5)

